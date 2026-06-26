# Installing Unity 2018.1.6f1 Headless on Linux

Reference for installing the exact Unity editor needed for this project on a headless Linux server. Verified on **Ubuntu 24.04 LTS**.

## Why this exact version

Unity's legacy networking (`NetworkView` / `[RPC]` / `OnSerializeNetworkView`) was last supported in Unity 2018.1. Version 2018.1.6f1 is the final patch of that line and is already installed on this system.

- **Version:** `2018.1.6f1`
- **Changeset:** `57cc34175ccf`
- **Installed at:** `~/unity-2018.1.6f1/`

## 1. Get the editor — direct `.tar.xz` (best for headless)

There is **no `.deb`** for this version. The tarball is the simplest install:

```bash
wget https://download.unity3d.com/download_unity/57cc34175ccf/LinuxEditorInstaller/Unity-2018.1.6f1.tar.xz
mkdir -p ~/unity-2018.1.6f1
tar -xf Unity-2018.1.6f1.tar.xz -C ~/unity-2018.1.6f1
ls ~/unity-2018.1.6f1/Editor/Unity    # the editor binary
```

(~803 MB download. The base editor includes Linux-standalone build support.)

## 2. Fix missing shared libraries (Ubuntu 22.04+/24.04)

The 2018 editor predates the removal of GConf:

```bash
cd /tmp
wget http://archive.ubuntu.com/ubuntu/pool/universe/g/gconf/gconf2-common_3.2.6-7ubuntu2_all.deb
wget http://archive.ubuntu.com/ubuntu/pool/universe/g/gconf/libgconf-2-4_3.2.6-7ubuntu2_amd64.deb
sudo apt install ./gconf2-common_3.2.6-7ubuntu2_all.deb ./libgconf-2-4_3.2.6-7ubuntu2_amd64.deb
```

Use `apt install ./file.deb`, **not** `dpkg -i`. To check for other missing libs:

```bash
ldd ~/unity-2018.1.6f1/Editor/Unity | grep "not found"
```

On a clean Ubuntu 24.04, `libgconf` was the only one missing.

## 3. xvfb — required to run the editor headless

Even with `-nographics`, the 2018 editor's Qt layer needs an X connection:

```bash
sudo apt install -y xvfb
xvfb-run -a ~/unity-2018.1.6f1/Editor/Unity ...
```

Built players run headless without xvfb — just `-batchmode -nographics`.

## 4. License activation

The editor needs an active license before it can build.

**Personal license (GUI sign-in):** Unity no longer supports offline activation for Personal. RDP/VNC into the box, launch the editor GUI, sign in, and let it pull a Personal license.

**Plus/Pro (manual `.alf`/`.ulf`):**

```bash
xvfb-run -a ~/unity-2018.1.6f1/Editor/Unity -batchmode -nographics -createManualActivationFile -quit
# upload .alf at https://license.unity3d.com/manual, download .ulf, then:
xvfb-run -a ~/unity-2018.1.6f1/Editor/Unity -batchmode -nographics -manualLicenseFile Unity_lic.ulf -quit
```

License persists at `~/.local/share/unity3d/Unity/Unity_lic.ulf`. Back it up.

## Verify

```bash
xvfb-run -a ~/unity-2018.1.6f1/Editor/Unity -batchmode -nographics -quit -logFile - 2>&1 | tail -20
```

A clean exit with license lines in the log means the editor is ready.
