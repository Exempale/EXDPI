LOCAL_PATH := $(call my-dir)
ROOT_PATH := $(LOCAL_PATH)
NATIVE_PATH := $(LOCAL_PATH)/../../../../native

# 1) hev-socks5-tunnel — даёт libhev-socks5-tunnel.so (TCP/UDP туннель из tun
# в локальный SOCKS5).
include $(NATIVE_PATH)/hev-socks5-tunnel/Android.mk

# 2) byedpi — даёт libbyedpi.so (локальный SOCKS5-сервер с DPI-десинком).
include $(CLEAR_VARS)
LOCAL_PATH := $(ROOT_PATH)
LOCAL_MODULE := byedpi

BYEDPI_REL := ../../../../native/byedpi
LOCAL_SRC_FILES := \
    $(BYEDPI_REL)/main.c \
    $(BYEDPI_REL)/proxy.c \
    $(BYEDPI_REL)/conev.c \
    $(BYEDPI_REL)/desync.c \
    $(BYEDPI_REL)/extend.c \
    $(BYEDPI_REL)/mpool.c \
    $(BYEDPI_REL)/packets.c \
    native-lib.c

LOCAL_C_INCLUDES := $(NATIVE_PATH)/byedpi
LOCAL_CFLAGS := -DDEFAULT_TTL=8 -D_GNU_SOURCE \
                -Wno-incompatible-pointer-types -Wno-error
LOCAL_LDLIBS := -llog
LOCAL_LDFLAGS += -Wl,-z,max-page-size=16384
LOCAL_LDFLAGS += -Wl,-z,common-page-size=16384
include $(BUILD_SHARED_LIBRARY)
