"""Авто-подбор стратегии zapret.

Идея: по очереди запускаем winws.exe с каждой стратегией ``general*.bat``,
после короткой паузы прогоняем TLS-handshake тест по набору заблокированных
доменов (см. app.dpi_test) и считаем счёт: сколько хостов открылось и с какой
средней задержкой. Побеждает стратегия с максимумом успешных хостов; при
равенстве — с меньшей средней задержкой.

Выбранную стратегию UI сохраняет в ``zapret_strategy_auto_result``; если
``zapret_strategy == AUTO_STRATEGY_ID`` — контроллер запускает именно её.

Прогон требует, чтобы основной zapret был остановлен (WinDivert-фильтр один
на систему) — UI-обёртка (ui_autostrategy.FirstRunWizard) сама останавливает
и восстанавливает состояние контроллера.
"""
from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Callable, List, Optional

from .dpi_test import DEFAULT_TARGETS, TestResult, _tls_handshake
from .zapret_runner import ZapretRunner, list_strategies

log = logging.getLogger("dpibypass.autostrategy")


# Спец-значение zapret_strategy: «выбирать лучшую автоматически».
AUTO_STRATEGY_ID = "auto"
AUTO_STRATEGY_LABEL = "Авто (подбор лучшей)"

# Сколько секунд даём winws.exe на установку WinDivert-фильтра перед тестом.
SETTLE_SECONDS = 1.6
# Таймаут TLS-handshake на один хост.
PER_HOST_TIMEOUT = 3.5


@dataclass
class StrategyScore:
    """Результат прогона одной стратегии."""

    strategy: str
    ok: int = 0
    total: int = 0
    avg_ms: int = 0
    error: str = ""
    results: List[TestResult] = field(default_factory=list)

    @property
    def perfect(self) -> bool:
        return self.total > 0 and self.ok == self.total


def is_auto(strategy_value: str) -> bool:
    return str(strategy_value or "").strip().lower() == AUTO_STRATEGY_ID


def resolve_strategy(cfg: dict) -> str:
    """Имя реального .bat для запуска с учётом режима «Авто».

    Если авто-подбор ещё не делался — используем дефолтную стратегию,
    чтобы программа всё равно работала.
    """
    value = str(cfg.get("zapret_strategy", "") or "")
    if not is_auto(value):
        return value or "general (ALT10).bat"
    auto = str(cfg.get("zapret_strategy_auto_result", "") or "")
    if auto and auto in list_strategies():
        return auto
    return "general (ALT10).bat"


def _test_targets_parallel(targets: List[str], timeout: float) -> List[TestResult]:
    """TLS-handshake по всем хостам параллельно (ускоряет прогон в ~N раз)."""
    out: List[TestResult] = []
    with ThreadPoolExecutor(max_workers=min(8, max(1, len(targets)))) as pool:
        futures = [pool.submit(_tls_handshake, host, 443, timeout) for host in targets]
        for fut in futures:
            try:
                out.append(fut.result())
            except Exception as exc:  # на всякий — _tls_handshake сам ловит всё
                log.exception("target test crashed")
                out.append(TestResult(host="?", ok=False, elapsed_ms=0, error=str(exc)))
    return out


def _score_from_results(strategy: str, results: List[TestResult]) -> StrategyScore:
    ok_results = [r for r in results if r.ok]
    avg_ms = int(sum(r.elapsed_ms for r in ok_results) / len(ok_results)) if ok_results else 0
    return StrategyScore(
        strategy=strategy,
        ok=len(ok_results),
        total=len(results),
        avg_ms=avg_ms,
        results=results,
    )


def evaluate_strategies(
    strategies: Optional[List[str]] = None,
    targets: Optional[List[str]] = None,
    custom_domains: Optional[List[str]] = None,
    game_mode: str = "normal",
    on_progress: Optional[Callable[[str, Optional[StrategyScore], int, int], None]] = None,
    should_stop: Optional[Callable[[], bool]] = None,
    stop_on_perfect: bool = True,
) -> List[StrategyScore]:
    """Прогнать все стратегии и вернуть их счёт (в порядке прогона).

    ``on_progress(strategy, score_or_None, index, total)`` вызывается дважды
    на стратегию: перед запуском (score=None) и после теста (с результатом).
    ``should_stop()`` — кооперативная отмена между стратегиями.
    ``stop_on_perfect`` — закончить раньше, если все хосты открылись.

    Вызывается из фонового потока; основной zapret должен быть остановлен.
    """
    strategies = list(strategies or list_strategies())
    targets = list(targets or DEFAULT_TARGETS)
    scores: List[StrategyScore] = []
    runner = ZapretRunner()
    total = len(strategies)

    for idx, strategy in enumerate(strategies):
        if should_stop and should_stop():
            log.info("auto-select cancelled at %s", strategy)
            break
        if on_progress:
            try:
                on_progress(strategy, None, idx, total)
            except Exception:
                log.exception("on_progress failed")

        score: StrategyScore
        try:
            runner.start(
                strategy,
                custom_domains=list(custom_domains or []),
                game_mode=game_mode,
            )
            time.sleep(SETTLE_SECONDS)
            if not runner.is_running:
                tail = "; ".join(runner.last_output_tail(3))
                score = StrategyScore(
                    strategy=strategy, ok=0, total=len(targets),
                    error=f"winws.exe не запустился: {tail or 'см. winws.log'}",
                )
            else:
                results = _test_targets_parallel(targets, PER_HOST_TIMEOUT)
                score = _score_from_results(strategy, results)
        except Exception as exc:
            log.exception("strategy %s failed", strategy)
            score = StrategyScore(strategy=strategy, ok=0, total=len(targets), error=str(exc))
        finally:
            try:
                runner.stop()
            except Exception:
                log.exception("runner stop failed")

        scores.append(score)
        log.info(
            "auto-select: %s → %d/%d ok, avg %d ms%s",
            strategy, score.ok, score.total, score.avg_ms,
            f" (error: {score.error})" if score.error else "",
        )
        if on_progress:
            try:
                on_progress(strategy, score, idx, total)
            except Exception:
                log.exception("on_progress failed")

        if stop_on_perfect and score.perfect:
            log.info("auto-select: perfect score, stopping early")
            break

    return scores


def pick_best(scores: List[StrategyScore]) -> Optional[StrategyScore]:
    """Лучшая стратегия: максимум успешных хостов, затем меньшая задержка."""
    valid = [s for s in scores if s.ok > 0]
    if not valid:
        return None
    return sorted(valid, key=lambda s: (-s.ok, s.avg_ms or 10 ** 9))[0]


def run_auto_select_async(
    on_progress: Optional[Callable[[str, Optional[StrategyScore], int, int], None]] = None,
    on_done: Optional[Callable[[List[StrategyScore], Optional[StrategyScore]], None]] = None,
    should_stop: Optional[Callable[[], bool]] = None,
    custom_domains: Optional[List[str]] = None,
    game_mode: str = "normal",
    targets: Optional[List[str]] = None,
) -> threading.Thread:
    """Полный авто-подбор в фоновом потоке.

    Колбэки вызываются из этого потока — UI обязан бунсить через after(0, …).
    """

    def _work() -> None:
        scores: List[StrategyScore] = []
        try:
            scores = evaluate_strategies(
                targets=targets,
                custom_domains=custom_domains,
                game_mode=game_mode,
                on_progress=on_progress,
                should_stop=should_stop,
            )
        except Exception:
            log.exception("auto-select crashed")
        best = pick_best(scores)
        if on_done:
            try:
                on_done(scores, best)
            except Exception:
                log.exception("on_done failed")

    th = threading.Thread(target=_work, daemon=True, name="auto-strategy")
    th.start()
    return th
