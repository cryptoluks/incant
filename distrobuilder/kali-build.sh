#!/usr/bin/env bash
set -euxo pipefail
incant up
incus image import kali-kali-rolling-amd64-cloud*.tar --reuse --alias kali/cloud --project default
incus image import kali-kali-rolling-amd64-xfce*.tar --reuse --alias kali/xfce --project default
incant destroy
