[app]
title = SampleBrain
project_dir = .
input_file = tools/windows/sample_brain_gui_entry.py
exec_directory = dist/packaging
project_file =
icon =

[python]
python_path =
packages = Nuitka==4.1.1
android_packages = buildozer==1.5.0,cython==0.29.33

[qt]
qml_files =
excluded_qml_plugins =
modules = Network,OpenGL,Qml,Quick,QuickControls2,QuickDialogs2,QuickLayouts
plugins = platforms,qml

[android]
wheel_pyside =
wheel_shiboken =
plugins =

[nuitka]
macos.permissions =
mode = standalone
extra_args = --quiet --noinclude-qt-translations --include-package=src --include-module=src.workbench_distributable_main --include-data-files=native/audio/build/bin/Release/samplebrain_audio.dll=samplebrain_audio.dll --windows-console-mode=disable --include-qt-plugins=platforms,qml --nofollow-import-to=torch --nofollow-import-to=transformers --nofollow-import-to=audio_separator --nofollow-import-to=sqlite_vec --nofollow-import-to=beat_this --nofollow-import-to=pytest --nofollow-import-to=tests --nofollow-import-to=PySide6.QtTest

[buildozer]
mode = debug
recipe_dir =
jars_dir =
ndk_path =
sdk_path =
local_libs =
arch =