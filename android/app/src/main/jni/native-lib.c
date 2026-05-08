/* EXDPI Android: JNI обёртка вокруг byedpi.
 *
 * byedpi — это userspace SOCKS5-сервер, который десинхронизирует TLS/HTTP
 * на первом пакете клиента и пересылает остальное на реальный адрес.
 * Мы запускаем его в фоновом потоке и закрываем listening-сокет, чтобы
 * остановить event_loop.
 */

#include <jni.h>
#include <pthread.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sys/socket.h>

#include <android/log.h>

#define LOG_TAG "byedpi-jni"
#define LOGI(...) __android_log_print(ANDROID_LOG_INFO, LOG_TAG, __VA_ARGS__)
#define LOGE(...) __android_log_print(ANDROID_LOG_ERROR, LOG_TAG, __VA_ARGS__)

extern int byedpi_main(int argc, char **argv);
extern volatile int byedpi_srvfd_global;

static pthread_mutex_t g_mu = PTHREAD_MUTEX_INITIALIZER;
static pthread_t g_thread;
static int g_running = 0;
static int g_argc = 0;
static char **g_argv = NULL;
static int g_last_rc = 0;

static void free_argv(int argc, char **argv) {
    if (!argv) return;
    for (int i = 0; i < argc; i++) free(argv[i]);
    free(argv);
}

static void *byedpi_thread(void *arg) {
    (void)arg;
    int argc = g_argc;
    char **argv = g_argv;
    LOGI("byedpi_main starting, argc=%d", argc);
    int rc = byedpi_main(argc, argv);
    LOGI("byedpi_main exited rc=%d", rc);

    pthread_mutex_lock(&g_mu);
    g_last_rc = rc;
    free_argv(argc, argv);
    g_argv = NULL;
    g_argc = 0;
    g_running = 0;
    pthread_mutex_unlock(&g_mu);
    return NULL;
}

JNIEXPORT jint JNICALL
Java_com_exdpi_android_core_ByeDpiNative_nativeStart(
        JNIEnv *env, jobject thiz, jobjectArray jargs) {
    pthread_mutex_lock(&g_mu);
    if (g_running) {
        pthread_mutex_unlock(&g_mu);
        return -2;
    }

    jsize n = (*env)->GetArrayLength(env, jargs);
    char **argv = (char **)calloc(n + 1, sizeof(char *));
    if (!argv) {
        pthread_mutex_unlock(&g_mu);
        return -3;
    }
    for (jsize i = 0; i < n; i++) {
        jstring s = (jstring)(*env)->GetObjectArrayElement(env, jargs, i);
        const char *str = (*env)->GetStringUTFChars(env, s, NULL);
        argv[i] = strdup(str ? str : "");
        if (str) (*env)->ReleaseStringUTFChars(env, s, str);
        (*env)->DeleteLocalRef(env, s);
    }
    argv[n] = NULL;

    g_argc = (int)n;
    g_argv = argv;
    g_running = 1;
    g_last_rc = 0;

    if (pthread_create(&g_thread, NULL, byedpi_thread, NULL) != 0) {
        free_argv((int)n, argv);
        g_argv = NULL;
        g_argc = 0;
        g_running = 0;
        pthread_mutex_unlock(&g_mu);
        return -4;
    }
    pthread_detach(g_thread);
    pthread_mutex_unlock(&g_mu);
    return 0;
}

JNIEXPORT jint JNICALL
Java_com_exdpi_android_core_ByeDpiNative_nativeStop(
        JNIEnv *env, jobject thiz) {
    (void)env;
    (void)thiz;
    pthread_mutex_lock(&g_mu);
    int fd = byedpi_srvfd_global;
    pthread_mutex_unlock(&g_mu);

    if (fd >= 0) {
        /* shutdown будит accept(), event_loop завершается с ошибкой и
         * выходит. close() выполняется самим byedpi внутри run(). */
        shutdown(fd, SHUT_RDWR);
    }

    /* Подождём небольшое время, чтобы поток успел выйти. */
    for (int i = 0; i < 50; i++) {
        pthread_mutex_lock(&g_mu);
        int running = g_running;
        pthread_mutex_unlock(&g_mu);
        if (!running) break;
        usleep(20 * 1000);
    }
    return 0;
}

JNIEXPORT jboolean JNICALL
Java_com_exdpi_android_core_ByeDpiNative_nativeIsRunning(
        JNIEnv *env, jobject thiz) {
    (void)env;
    (void)thiz;
    pthread_mutex_lock(&g_mu);
    int running = g_running;
    pthread_mutex_unlock(&g_mu);
    return running ? JNI_TRUE : JNI_FALSE;
}
