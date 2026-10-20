[app]
title = PhoneMouse
package.name = phonemouse
package.domain = org.example
source.dir = .
source.include_exts = py
version = 0.1
requirements = python3==3.11.5,hostpython3==3.11.5,kivy==2.3.0,plyer,pyjnius
orientation = portrait
fullscreen = 0
android.permissions = INTERNET,ACCESS_NETWORK_STATE,ACCESS_WIFI_STATE,CHANGE_WIFI_MULTICAST_STATE
android.api = 33
android.minapi = 24
android.archs = arm64-v8a
android.accept_sdk_license = True
p4a.branch = v2024.01.21

[buildozer]
log_level = 2
warn_on_root = 1
