import tkinter as tk
import threading, queue, time
import serial
import gestures

q = queue.Queue()
stop = threading.Event()


def my_print(*args, **kwargs):
    # gestures.py ke print() ko UI ke log mein bhejo
    q.put(("log", " ".join(str(a) for a in args)))


gestures.print = my_print


def reader():
    # Thread 1: sensor data padhta hai aur gesture detect karta hai
    try:
        ser = serial.Serial(gestures.PORT, 9600, timeout=1)
    except Exception as e:
        q.put(("error", str(e)))
        return
    n = 0
    t0 = time.time()
    while not stop.is_set():
        line = ser.readline().decode(errors="ignore").strip()
        if "," not in line:
            continue
        try:
            d = [int(x) for x in line.split(",")]
        except ValueError:
            continue
        if len(d) != 2:
            continue
        gestures.children[:] = [c for c in gestures.children if c.poll() is None]
        now = time.time()
        gestures.handle(d, now)
        q.put(("dist", d[0], d[1]))
        n += 1
        if now - t0 >= 1:
            q.put(("rate", n / (now - t0)))
            n = 0
            t0 = now
    ser.close()


# ---------------- UI (Thread 2: main thread) ----------------
root = tk.Tk()
root.title("Air Control - Gesture Dashboard")
root.geometry("520x560")
root.configure(bg="#f4f4f4")

BAR_W, BAR_H, MAX_CM = 400, 26, 50

tk.Label(root, text="Air Control - Gesture Dashboard", font=("Arial", 15, "bold"),
         bg="#f4f4f4").pack(pady=(10, 4))


def make_sensor(title):
    tk.Label(root, text=title, font=("Arial", 11, "bold"), bg="#f4f4f4").pack(anchor="w", padx=50)
    c = tk.Canvas(root, width=BAR_W, height=BAR_H, bg="white", highlightthickness=1,
                  highlightbackground="#999")
    c.pack(padx=50, anchor="w")
    lbl = tk.Label(root, text="-- (hath nahi)", font=("Arial", 11), bg="#f4f4f4")
    lbl.pack(anchor="w", padx=50)
    return c, lbl


c1, l1 = make_sensor("Sensor 1 (Control: tap / double tap / hold)")
c2, l2 = make_sensor("Sensor 2 (Volume)")


def draw_bar(canvas, label, d):
    canvas.delete("all")
    if d >= 999 or d <= 2:
        label.config(text="-- (hath nahi)")
    else:
        w = min(d, MAX_CM) / MAX_CM * BAR_W
        color = "#2e9e4f" if d < gestures.NEAR_IN else ("#e0a030" if d < gestures.SEEN else "#9aa0a6")
        canvas.create_rectangle(0, 0, w, BAR_H, fill=color, width=0)
        label.config(text=f"{d} cm")
    for cm in (gestures.NEAR_IN, gestures.SEEN):
        x = cm / MAX_CM * BAR_W
        canvas.create_line(x, 0, x, BAR_H, fill="#555", dash=(2, 2))


tk.Label(root, text="Hari = paas (<15 cm)   Narangi = nazar aaya (<30 cm)",
         font=("Arial", 9), bg="#f4f4f4", fg="#555").pack(pady=(2, 6))

tk.Label(root, text="Last gesture", font=("Arial", 11, "bold"), bg="#f4f4f4").pack()
gesture_lbl = tk.Label(root, text="--", font=("Arial", 26, "bold"), bg="#f4f4f4", fg="#1a5fb4")
gesture_lbl.pack()
action_lbl = tk.Label(root, text="", font=("Arial", 9), bg="#f4f4f4", fg="#555")
action_lbl.pack()

mode_lbl = tk.Label(root, text="Volume mode: OFF", font=("Arial", 11, "bold"), bg="#f4f4f4")
mode_lbl.pack(pady=(8, 0))
vol_canvas = tk.Canvas(root, width=BAR_W, height=20, bg="white", highlightthickness=1,
                       highlightbackground="#999")
vol_canvas.pack()
vol_lbl = tk.Label(root, text="Volume: --", font=("Arial", 10), bg="#f4f4f4")
vol_lbl.pack()

log = tk.Text(root, height=8, width=62, font=("Courier", 9), state="disabled")
log.pack(padx=10, pady=(8, 2))
rate_lbl = tk.Label(root, text="Readings/sec: --", font=("Arial", 9), bg="#f4f4f4", fg="#555")
rate_lbl.pack()


def add_log(text):
    log.config(state="normal")
    log.insert("end", time.strftime("%H:%M:%S ") + text + "\n")
    log.see("end")
    log.config(state="disabled")


def set_volume_bar(pct):
    vol_canvas.delete("all")
    vol_canvas.create_rectangle(0, 0, pct / 100 * BAR_W, 20, fill="#1a5fb4", width=0)
    vol_lbl.config(text=f"Volume: {pct}%")


def poll():
    try:
        while True:
            item = q.get_nowait()
            kind = item[0]
            if kind == "dist":
                draw_bar(c1, l1, item[1])
                draw_bar(c2, l2, item[2])
            elif kind == "rate":
                rate_lbl.config(text=f"Readings/sec: {item[1]:.1f}")
            elif kind == "error":
                add_log("ERROR: " + item[1])
                gesture_lbl.config(text="PORT ERROR", fg="#c01c28")
            elif kind == "log":
                t = item[1]
                add_log(t)
                if t.startswith("GESTURE:"):
                    gesture_lbl.config(text=t.split(":", 1)[1].strip(), fg="#1a5fb4")
                    action_lbl.config(text="")
                elif t.strip().startswith("->"):
                    action_lbl.config(text=t.strip())
                elif t.startswith("VOLUME MODE ON"):
                    mode_lbl.config(text="Volume mode: ON", fg="#2e9e4f")
                elif t.startswith("VOLUME MODE OFF"):
                    mode_lbl.config(text="Volume mode: OFF", fg="black")
                elif t.startswith("VOLUME:"):
                    set_volume_bar(int(t.split(":")[1].strip().rstrip("%")))
    except queue.Empty:
        pass
    root.after(50, poll)


def on_close():
    stop.set()
    root.destroy()


root.protocol("WM_DELETE_WINDOW", on_close)
threading.Thread(target=reader, daemon=True).start()
poll()
root.mainloop()
