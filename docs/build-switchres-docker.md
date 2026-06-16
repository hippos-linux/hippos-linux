# Build switchres on Mac (Docker required)

Docker Desktop must be running.

```bash
cd ~/hippos-linux
docker run --rm --platform linux/amd64 -v "$PWD:/work" -w /work debian:trixie bash -c '
  set -e
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq && apt-get install -y -qq git build-essential libxrandr-dev libx11-dev libdrm-dev
  git clone --depth=1 --branch v2.2.2 https://github.com/antonioginer/switchres.git /tmp/switchres
  make -C /tmp/switchres -j$(nproc)
  install -m755 /tmp/switchres/switchres /work/artifacts/tools/switchres/bin/switchres
'
rsync -av artifacts/tools/switchres/bin/switchres root@hippos.local:/usr/bin/
ssh root@hippos.local 'DISPLAY=:0 switchres 640 480 60 -i /etc/switchres.ini; echo exit=$?'
```

If exit is still 139, compare with Batocera CRT Script switchres build or try a different switchres tag.
