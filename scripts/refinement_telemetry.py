"""Continuous driver-memory sampling; fail closed on telemetry loss or 80%."""
import csv,os,signal,subprocess,threading,time
from pathlib import Path
from extension_state import write

class Monitor:
    def __init__(self,path):
        self.path=Path(path);self.stop=threading.Event();self.ready=threading.Event()
        self.failure=None;self.peak=0.;self.thread=threading.Thread(target=self.capture,daemon=True)
    def capture(self):
        query="index,uuid,name,memory.total,memory.used,utilization.gpu,power.draw,driver_version,clocks.sm,clocks.mem,power.limit,temperature.gpu,clocks_event_reasons.active"
        try:
            with self.path.open("x",buffering=1) as f:
                f.write("epoch,index,uuid,name,total_MiB,used_MiB,util_percent,power_W,driver,SM_MHz,memory_MHz,power_limit_W,temp_C,event_reasons\n")
                while not self.stop.is_set():
                    output=subprocess.run(["nvidia-smi","--query-gpu="+query,"--format=csv,noheader,nounits"],
                                           check=True,capture_output=True,text=True,timeout=10).stdout
                    lines=list(csv.reader(output.splitlines()))
                    if not lines:raise ValueError("no device telemetry")
                    saw_device=False
                    for row in lines:
                        if int(row[0])!=0:continue
                        saw_device=True
                        fraction=float(row[4])/float(row[3]);self.peak=max(self.peak,fraction)
                        f.write(str(time.time())+","+",".join(row)+"\n")
                        if not 0<=fraction<=.8:raise ValueError("driver_memory_80_percent")
                    if not saw_device:raise ValueError("device zero missing from telemetry")
                    self.ready.set();self.stop.wait(.25)
        except Exception as exc:
            self.failure=type(exc).__name__+": "+str(exc)
            write(self.path.with_suffix(".failure.json"),dict(failure=self.failure,at_epoch=time.time()))
            self.ready.set()
            # This monitor runs only inside the owned worker/analysis process.
            os.kill(os.getpid(),signal.SIGTERM)
    def start(self):
        self.thread.start()
        if not self.ready.wait(12):raise TimeoutError("memory monitor startup")
        if self.failure:raise ValueError(self.failure)
    def finish(self):
        self.stop.set();self.thread.join(12)
        if self.thread.is_alive() or self.failure:raise ValueError("telemetry incomplete")
        return dict(peak_driver_used_fraction=self.peak,sampling_interval_s=.25,
                    limitation="periodic samples do not bound transients between samples")
