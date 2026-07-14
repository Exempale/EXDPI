"""Запуск Sing-box (sing-box.exe run -c <config>) как глобального TUN-VPN.

Архитектурно — близкий родственник ``ZapretRunner``: тот же шаблон
``subprocess.Popen`` + reader-поток для логов + корректный ``stop()``.
Разница в том, что здесь:

* бинарник — ``resources/singbox/sing-box.exe``;
* конфиг генерируется из ссылки-подключения (vless/ss) перед стартом
  (см. ``app.singbox_config``);
* sing-box в режиме TUN требует прав администратора — EXDPI и так
  запускается с ``uac_admin=True`` (см. build.spec), так что дополнительных
  elevation-танцев не нужно;
* процесс sing-box держит TUN-адаптер; два экземпляра одновременно
  конфликтуют, поэтому ``start()`` сначала убивает осиротевшие процессы.

API:
    runner = SingboxRunner()
    runner.start("vless://...")         # сгенерировать конфиг + стартовать
    runner.is_running
    runner.last_output_tail()           # последние строки stdout (для ошибок)
    runner.stop()                       # terminate → wait → kill
"""
from __future__ import annotations

import logging
import subprocess
import sys
import threading
from typing import Callable, List, Optional

from . import paths
from .singbox_config import ParseError, save_config

log = logging.getLogger("dpibypass.singbox")

# Windows: не показывать чёрное окно консоли и дать возможность корректно
# передать Ctrl-Break (CREATE_NEW_PROCESS_GROUP) — sing-box ловит SIGINT.
CREATE_NO_WINDOW = 0x08000000
CREATE_NEW_PROCESS_GROUP = 0x00000200


def _kill_orphan_singbox() -> int:
    """Убить осиротевшие sing-box.exe перед запуском нового.

    TUN-интерфейс и маршруты — singleton-ресурс: два процесса с
    ``auto_route=true`` дерутся за ``172.19.0.1/30`` и маршрут по умолчанию.
    После краха/принудительного закрытия прошлый sing-box может остаться
    жить и держать адаптер «EXDPI-Tun».
    """
    if sys.platform != "win32":
        return 0
    killed = 0
    try:
        result = subprocess.run(
            ["taskkill", "/F", "/IM", "sing-box.exe"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
            creationflags=CREATE_NO_WINDOW,
            timeout=5,
        )
        if result.returncode == 0:
            out = result.stdout.decode("cp866", errors="replace")
            killed = out.count("PID")
            if killed:
                log.info("killed orphan sing-box.exe (%d)", killed)
    except Exception:
        log.exception("kill orphan sing-box failed")
    return killed


class SingboxRunner:
    """Менеджер жизненного цикла sing-box.exe (TUN-VPN)."""

    def __init__(self) -> None:
        self._proc: Optional[subprocess.Popen] = None
        self._lock = threading.Lock()
        self._uri: Optional[str] = None
        self._config_path: Optional[str] = None
        # хвост stdout — для диагностики rc != 0
        self._out_tail: List[str] = []
        self._tail_lock = threading.Lock()

    # ── observability ────────────────────────────────────────────────────
    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._proc is not None and self._proc.poll() is None

    @property
    def current_uri(self) -> Optional[str]:
        """Ссылка, на которой сейчас работает (или работала) runner."""
        with self._lock:
            return self._uri

    @property
    def config_path(self) -> Optional[str]:
        with self._lock:
            return self._config_path

    def last_output_tail(self, lines: int = 10) -> List[str]:
        """Последние строки stdout sing-box текущей/прошлой сессии."""
        with self._tail_lock:
            return list(self._out_tail[-lines:])

    # ── lifecycle ────────────────────────────────────────────────────────
    def start(
        self,
        uri: str,
        on_exit: Optional[Callable[[int], None]] = None,
        config_path: Optional[str] = None,
        options: Optional[dict] = None,
    ) -> None:
        """Сгенерировать конфиг из ссылки и стартовать sing-box.

        ``uri``         — vless:// или ss:// ;
        ``config_path`` — куда положить singbox_config.json (по умолчанию
                          %APPDATA%/EXDPI/singbox_config.json);
        ``on_exit``     — колбэк в потоке-наблюдателе после завершения
                          процесса (например, для обновления UI).
        """
        # 1) валидируем и пишем конфиг ВНЕ lock — это I/O и потенциально
        #    долгий парсинг; lock нужен только для защиты _proc.
        try:
            target = (save_config(uri, path=config_path, options=options)
                      if config_path else save_config(uri, options=options))
        except ParseError:
            raise
        except Exception as exc:
            log.exception("singbox config generation failed")
            raise RuntimeError(f"не удалось создать конфиг sing-box: {exc}") from exc

        with self._lock:
            if self._proc and self._proc.poll() is None:
                log.info("sing-box уже запущен, игнорируем повторный start")
                return

            # убиваем осиротевшие sing-box.exe — иначе TUN занят.
            _kill_orphan_singbox()

            binary = paths.singbox_binary()
            if not binary.exists():
                raise RuntimeError(f"sing-box.exe не найден: {binary}")

            cmd = [str(binary), "run", "-c", str(target)]
            log.info("sing-box start: %s", target.name)
            log.debug("argv: %s", cmd)

            kw: dict = dict(
                cwd=str(paths.singbox_root()),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
            )
            if sys.platform == "win32":
                kw["creationflags"] = CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP

            try:
                self._proc = subprocess.Popen(cmd, **kw)
            except Exception as exc:
                log.error("sing-box launch failed: %s", exc)
                raise

            self._uri = uri
            self._config_path = str(target)
            with self._tail_lock:
                self._out_tail = []

            threading.Thread(
                target=self._pump_output,
                args=(self._proc,),
                daemon=True,
                name="singbox-log",
            ).start()

        if on_exit:
            threading.Thread(
                target=self._wait,
                args=(on_exit,),
                daemon=True,
                name="singbox-wait",
            ).start()

    def _pump_output(self, proc: subprocess.Popen) -> None:
        """Читать stdout/stderr sing-box построчно и писать в общий лог.

        Хвост копится в памяти — при rc != 0 его покажет контроллер/UI.
        """
        try:
            from .logs import winws_logger  # noqa: F401  (не нужен здесь)
        except Exception:
            pass
        # у sing-box свой лог пишем в тот же «dpibypass.singbox» логгер,
        # отдельный файл не заводим — пока объём небольшой.
        stream = proc.stdout
        if stream is None:
            return
        log.info("─── sing-box session start (pid=%s) ───", proc.pid)
        try:
            for raw in iter(stream.readline, b""):
                try:
                    line = raw.decode("utf-8").rstrip("\r\n")
                except UnicodeDecodeError:
                    line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
                if not line.strip():
                    continue
                log.info("%s", line)
                with self._tail_lock:
                    self._out_tail.append(line)
                    if len(self._out_tail) > 60:
                        self._out_tail = self._out_tail[-60:]
        except Exception:
            log.exception("sing-box output pump failed")
        finally:
            try:
                stream.close()
            except Exception:
                pass
            log.info("─── sing-box session end ───")

    def _wait(self, on_exit: Callable[[int], None]) -> None:
        try:
            rc = self._proc.wait() if self._proc else 0  # type: ignore[union-attr]
        except Exception:
            rc = -1
        if rc != 0:
            tail = self.last_output_tail(12)
            if tail:
                log.error("sing-box output (last %d lines):", len(tail))
                for line in tail:
                    log.error("  %s", line)
        try:
            on_exit(rc)
        except Exception:
            pass

    def stop(self, timeout: float = 5.0) -> None:
        """Корректно завершить sing-box: terminate → wait → kill."""
        with self._lock:
            proc = self._proc
            self._proc = None
            # uri/config_path НЕ обнуляем — UI может захотеть показать
            # «последняя ссылка» после остановки.

        if not proc or proc.poll() is not None:
            # даже если процесса уже нет — добиваем осиротевшие, чтобы
            # TUN-адаптер точно освободился.
            _kill_orphan_singbox()
            return

        log.info("sing-box stop")
        # Сначала Ctrl-Break (мы стартовали с CREATE_NEW_PROCESS_GROUP) —
        # sing-box корректно снимет TUN/маршруты. Это мягче terminate().
        if sys.platform == "win32":
            try:
                proc.send_signal(
                    __import__("signal").CTRL_BREAK_EVENT  # type: ignore[attr-defined]
                )
            except Exception:
                pass
        try:
            proc.terminate()
        except Exception:
            pass

        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            try:
                proc.kill()
            except Exception:
                pass
        except Exception:
            pass

        # на всякий случай добиваем любые осиротевшие sing-box.exe — иначе
        # следующий start() словит «interface already exists».
        _kill_orphan_singbox()
