@echo off
REM batch file for generating the windows .exe installer
set PYTHON="c:\Python26\python.exe"
cd doc\en
%PYTHON% ..\rest2htmlnav --stylesheet-path=lc.css --time documentation.txt documentation.html
%PYTHON% ..\rest2htmlnav --stylesheet-path=lc.css --time index.txt index.html
%PYTHON% ..\rest2htmlnav --stylesheet-path=lc.css --time install.txt install.html
%PYTHON% ..\rest2htmlnav --stylesheet-path=lc.css --time other.txt other.html
%PYTHON% ..\rest2htmlnav --stylesheet-path=lc.css --time upgrading.txt upgrading.html
%PYTHON% ..\bfknav.py
cd ..\..
%PYTHON% setup.py clean --all
%PYTHON% setup.py sdist --manifest-only
:: %PYTHON% setup.py build -c mingw32 bdist_wininst -b hase.bmp --install-script install-linkchecker.py
%PYTHON% setup.py build -c mingw32 py2exe
REM start resource editor for .exe icon
REM "%PROGRAMFILES%\XN Resource Editor\XNResourceEditor.exe"
