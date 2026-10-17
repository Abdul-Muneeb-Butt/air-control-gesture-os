import serial, time, subprocess

PORT = "/dev/ttyUSB0"

# ---------- Distance settings (cm) ----------
SEEN = 30          # isse kam = sensor ne hath dekh liya (swipe direction ke liye)
NEAR_IN = 15       # isse kam = hath paas
NEAR_OUT = 20      # isse zyada = hath gaya
CONFIRM = 2        # lagatar readings (noise filter)

# ---------- Time settings (seconds) ----------
TAP_MAX = 0.7      # itni jaldi wapas = tap
WAIT = 0.6         # tap ke baad itna ruko: double tap ya swipe to nahi
HOLD_TIME = 1.5    # sensor 1 par itni der = hold
SWIPE_WINDOW = 0.6 # dono sensors is waqt ke andar = swipe
MIN_GAP = 0.03     # isse kam gap = dono ek sath
MIN_SEEN_GAP = 0.03
COOLDOWN = 0.6     # ek gesture ke baad itni der doosra nahi

# ---------- Volume settings ----------
VOL_MIN = 5        # cm: 0% volume
VOL_MAX = 30       # cm: 100% volume
HOVER_TIME = 0.8   # sec: hath itni der sthir = volume mode on

# ---------- Kaun sa gesture kya kare (yahan badlo) ----------
ACTIONS = {
    "TAP":         ["firefox"],
    "DOUBLE TAP":  ["nautilus"],
    "HOLD":        ["pactl", "set-sink-mute", "@DEFAULT_SINK@", "toggle"],
    "SWIPE RIGHT": ["gnome-calculator"],
    "SWIPE LEFT":  ["gnome-terminal"],
}

# ---------- State ----------
near = [False, False]
cnt = [0, 0]
t_in = [0.0, 0.0]
used = [False, False]
seen = [False, False]
seen_t = [0.0, 0.0]
cand_n = [0, 0]
cand_t = [0.0, 0.0]
far_n = [0, 0]
tap_pending = False
tap_time = 0.0
last_g = 0.0
hover_start = None
hover_ref = 0
engaged = False
out_n = 0
last_vol = -100
last_vol_t = 0.0
recent = []
children = []


def fire(name):
    global last_g
    now = time.time()
    if now - last_g < COOLDOWN:
        return
    last_g = now
    print("GESTURE:", name)
    cmd = ACTIONS.get(name)
    if cmd:
        try:
            # naya child process banta hai (fork + exec)
            p = subprocess.Popen(cmd, stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL)
            children.append(p)
            print(f"  -> action: {' '.join(cmd)} (PID {p.pid})")
        except OSError:
            print(f"  -> '{cmd[0]}' nahi mila (install nahi hai ya naam alag hai)")


def track_seen(i, v, now):
    # hath sensor ke 30 cm ke andar kab aaya (swipe ki direction ke liye)
    if 2 < v < SEEN:
        far_n[i] = 0
        if not seen[i]:
            if cand_n[i] == 0:
                cand_t[i] = now
            cand_n[i] += 1
            if cand_n[i] >= CONFIRM:
                seen[i] = True
                seen_t[i] = cand_t[i]
    else:
        cand_n[i] = 0
        if seen[i] and (v >= SEEN + 5 or v <= 2):
            far_n[i] += 1
            if far_n[i] >= CONFIRM:
                seen[i] = False
                far_n[i] = 0


def check_swipe(i, now):
    global tap_pending
    j = 1 - i
    if engaged or used[j] or now - t_in[j] >= SWIPE_WINDOW:
        return
    if seen[0] and seen[1] and abs(seen_t[0] - seen_t[1]) >= MIN_SEEN_GAP:
        s1_first = seen_t[0] < seen_t[1]
    elif now - t_in[j] >= MIN_GAP:
        s1_first = (j == 0)
    else:
        return  # dono ek sath aaye: swipe nahi
    fire("SWIPE RIGHT" if s1_first else "SWIPE LEFT")
    used[0] = used[1] = True
    tap_pending = False


def register_tap(now):
    global tap_pending, tap_time
    if tap_pending and now - tap_time < WAIT:
        tap_pending = False
        fire("DOUBLE TAP")
    else:
        tap_pending = True
        tap_time = now


def set_volume(d2, now):
    global last_vol, last_vol_t
    recent.append(d2)
    del recent[:-3]
    m = sorted(recent)[len(recent) // 2]   # median = noise kam
    pct = int(round((m - VOL_MIN) * 100 / (VOL_MAX - VOL_MIN)))
    pct = max(0, min(100, pct))
    if abs(pct - last_vol) >= 5 and now - last_vol_t >= 0.2:
        last_vol, last_vol_t = pct, now
        try:
            subprocess.run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{pct}%"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           timeout=2)
        except (OSError, subprocess.SubprocessError):
            pass
        print(f"VOLUME: {pct}%")


def handle_volume(d2, now):
    global hover_start, hover_ref, engaged, out_n, last_vol
    in_range = VOL_MIN <= d2 <= VOL_MAX and not near[0]
    if not in_range:
        out_n += 1
        if out_n >= CONFIRM:
            hover_start = None
            if engaged:
                engaged = False
                print("VOLUME MODE OFF")
        return
    out_n = 0
    if hover_start is None:
        hover_start = now
        hover_ref = d2
    if not engaged:
        if abs(d2 - hover_ref) > 3:
            hover_start = now
            hover_ref = d2
        elif now - hover_start >= HOVER_TIME:
            engaged = True
            recent.clear()
            last_vol = -100
            print("VOLUME MODE ON (hath upar = zyada, neeche = kam)")
    if engaged:
        set_volume(d2, now)


def handle(d, now):
    global tap_pending
    for i in (0, 1):
        v = d[i]
        track_seen(i, v, now)
        is_near = 2 < v < NEAR_IN
        is_far = v >= NEAR_OUT or v <= 2

        if not near[i]:
            cnt[i] = cnt[i] + 1 if is_near else 0
            if cnt[i] >= CONFIRM:
                near[i] = True
                cnt[i] = 0
                t_in[i] = now
                used[i] = False
                check_swipe(i, now)
        else:
            cnt[i] = cnt[i] + 1 if is_far else 0
            if cnt[i] >= CONFIRM:
                near[i] = False
                cnt[i] = 0
                if i == 0 and not used[0] and not engaged and now - t_in[0] < TAP_MAX:
                    register_tap(now)
            elif i == 0 and not used[0] and not engaged and now - t_in[0] >= HOLD_TIME:
                fire("HOLD")
                used[0] = True

    handle_volume(d[1], now)

    if tap_pending and now - tap_time >= WAIT:
        tap_pending = False
        fire("TAP")


if __name__ == "__main__":
    ser = serial.Serial(PORT, 9600, timeout=1)
    print("Ready. Band karne ke liye Ctrl + C dabao.")
    try:
        while True:
            line = ser.readline().decode(errors="ignore").strip()
            if "," not in line:
                continue
            try:
                d = [int(x) for x in line.split(",")]
            except ValueError:
                continue
            if len(d) != 2:
                continue
            children[:] = [c for c in children if c.poll() is None]  # finished child reap
            handle(d, time.time())
    except KeyboardInterrupt:
        print("\nBand.")
