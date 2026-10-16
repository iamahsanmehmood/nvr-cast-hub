# 📹 Multi-Brand NVR & CCTV Setup Guide (`v0.1.0-beta`)

**NVR Cast Hub** broadcasts a universal, hardware-compatible dual RTSP stream (`/main` for HD Full-Screen and `/sub` for Multi-Camera Grid View) encoded in **H.264 Baseline (`0 B-frames`)** with **G.711u (`pcm_mulaw` 8kHz) / G.711a / AAC** audio.

Because it speaks standard RTSP/RTP over TCP & UDP (plus includes a built-in compatibility patch for Hikvision's custom RTSP parser), it works with **virtually any NVR, DVR with IP channels, or VMS on your local network**.

---

## 🔗 Your PC's Universal RTSP Stream URLs

When `NVR_Cast_Hub.exe` (or `python nvr_cast_app.py`) is running on your PC (e.g. `192.168.100.49`):

- **Main Stream (HD 720p/1080p):** `rtsp://<YOUR_PC_IP>:554/main`
- **Sub Stream (SD 360p Grid):** `rtsp://<YOUR_PC_IP>:554/sub`
- **Browser Web Cast Studio:** `http://localhost:8090` (or `http://<YOUR_PC_IP>:8090` on any phone/laptop)

---

## 1️⃣ Hikvision NVR Setup (Special Focus & Tested Live)

Hikvision NVRs require defining a **Custom Protocol** once so the NVR knows to pull `/main` for Full-Screen and `/sub` for Multi-Camera Grid View:

1. On your Hikvision NVR monitor (or Web UI at `http://<NVR_IP>`), go to:
   - **Configuration (or System)** $\rightarrow$ **Camera Management** $\rightarrow$ **IP Camera** $\rightarrow$ **Custom Protocol**
2. Select **Custom Protocol 1** and configure:
   - **Protocol Name:** `NVRCastHub` (or `RTSP`)
   - **Enable Main Stream:** Checked ✅
     - **Protocol:** `RTSP` | **Transfer Protocol:** `TCP` (or `AUTO`) | **Port:** `554`
     - **Stream Path:** `/main` (or `main`)
   - **Enable Sub-Stream:** Checked ✅
     - **Protocol:** `RTSP` | **Transfer Protocol:** `TCP` (or `AUTO`) | **Port:** `554`
     - **Stream Path:** `/sub` (or `sub`)
   - Click **Save / Apply**.
3. Click **Add (Custom Add)** in IP Camera Management:
   - **IP Camera Address:** `<YOUR_PC_IP>` (e.g., `192.168.100.49`)
   - **Protocol:** Select `NVRCastHub` (the Custom Protocol you created)
   - **Management Port:** `554`
   - **Username:** `admin` | **Password:** `12345` *(dummy required fields; authentication is open on LAN)*
4. **Enable Audio on Monitor:** Click the channel tile on your NVR monitor and click the **Speaker Icon (Audio On)**. Keep Audio Codec in NVR Cast Hub set to **`pcm_mulaw (G.711u CCTV)`**.

---

## 2️⃣ Dahua / Lorex / Amcrest NVR Setup

Dahua, Lorex, and Amcrest NVRs allow adding direct RTSP URLs under the **"Customized"** manufacturer option:

1. Open your NVR menu: **Settings** $\rightarrow$ **Camera** $\rightarrow$ **Registration (Camera List)** $\rightarrow$ **Manual Add**.
2. Set **Manufacturer** to **`Customized`** (or **`General` / `RTSP`**).
3. Enter:
   - **Main Stream RTSP URL:** `rtsp://<YOUR_PC_IP>:554/main`
   - **Sub Stream RTSP URL:** `rtsp://<YOUR_PC_IP>:554/sub`
   - **Username:** `admin` | **Password:** `12345`
4. Click **Save**. For audio on Dahua/Amcrest HDMI output, either **`pcm_mulaw (G.711u)`**, **`pcm_alaw (G.711a)`**, or **`aac`** works natively.

---

## 3️⃣ Uniview (UNV) NVR Setup

1. Go to **Setup** $\rightarrow$ **Camera** $\rightarrow$ **Camera** $\rightarrow$ **Custom Add**.
2. Set **Protocol** to **`Custom 1`** $\rightarrow$ click **Protocol** to configure:
   - **Protocol Name:** `NVRCast`
   - **Port:** `554` | **Transfer Protocol:** `TCP`
   - **Main Stream:** `rtsp://<YOUR_PC_IP>:554/main`
   - **Sub Stream:** `rtsp://<YOUR_PC_IP>:554/sub`
3. Add the camera with IP `<YOUR_PC_IP>` and select `NVRCast`.

---

## 4️⃣ Reolink / Swann / Annke / Night Owl & ONVIF/RTSP NVRs

1. Open **Channel Management / Add Camera** $\rightarrow$ select **RTSP / Custom / Manual IP**.
2. Provide the Main Stream (`rtsp://<YOUR_PC_IP>:554/main`) and Sub Stream (`rtsp://<YOUR_PC_IP>:554/sub`) on port `554`.

---

## 5️⃣ Synology Surveillance Station / Blue Iris / Frigate / VLC

- **Synology Surveillance Station:** Add Camera $\rightarrow$ Brand: `[User Define]` $\rightarrow$ Type: `Streaming - RTSP` $\rightarrow$ Path: `<YOUR_PC_IP>:554/main`.
- **Blue Iris:** Add New Camera $\rightarrow$ Network IP $\rightarrow$ `rtsp://<YOUR_PC_IP>:554/main`.
- **VLC Media Player / Smart TVs:** Media $\rightarrow$ Open Network Stream $\rightarrow$ `rtsp://<YOUR_PC_IP>:554/main`.
