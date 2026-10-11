#!/usr/bin/env python3
"""Independent ownership-bound guard. Local rehearsals never access Vast."""
import argparse,json,os,signal,time
from pathlib import Path
def write(path,data):
    # No NumPy/PyTorch dependency in the provider safety process.
    path=Path(path)
    temporary=path.with_name(path.name+".guard-"+str(os.getpid())+".tmp")
    temporary.write_text(json.dumps(data,indent=2,allow_nan=False)+"\n")
    temporary.replace(path)


def birth(pid):
    try:return Path(f"/proc/{int(pid)}/stat").read_text().rsplit(")",1)[1].split()[19]
    except (FileNotFoundError,ProcessLookupError):return None
def same(pid,stamp):
    return stamp is not None and birth(pid)==stamp
def kill_owned(process):
    pid=process["pid"]
    if same(pid,process["birth"]):
        try:os.killpg(pid,signal.SIGKILL)
        except ProcessLookupError:pass

def main(directory):
    out=Path(directory);state=json.loads((out/"controller_state.json").read_text())
    mode=state["mode"]
    if mode not in ("local-rehearsal","vast"):raise ValueError("unknown guard mode")
    if mode=="vast":
        if not state.get("provisioning_authorized") or not state["label"].startswith("SpectraNS-3D-v3-refinement-"):
            raise ValueError("unguarded instance ownership")
        if not 0<state["deadline_epoch"]-state["started_epoch"]<=7200:raise ValueError("invalid lifetime")
        if state.get("inject"):raise ValueError("fault hooks forbidden in Vast mode")
    write(out/"guard_ready.json",dict(pid=os.getpid(),mode=mode,at_epoch=time.time()))
    while True:
        state=json.loads((out/"controller_state.json").read_text())
        if (out/"termination.json").exists() and json.loads((out/"termination.json").read_text()).get("verified"):return
        reason=None
        if not same(state["controller_pid"],state["controller_birth"]):reason="controller_absent"
        elif time.time()>=state["deadline_epoch"]:reason="deadline"
        elif mode=="local-rehearsal" and state.get("inject"):
            stage=state.get("phase")
            if stage==state["inject"] or (state["inject"]=="checkpoint_collection" and stage=="exploration"):
                if state["inject"] in ("coarse","fine","exploration"):
                    marker=Path(state["worker_progress"])
                    if marker.exists() and json.loads(marker.read_text()).get("t",0)>state.get("worker_start_t",0)+1e-14:reason="injected_"+state["inject"]
                else:
                    marker=Path(state.get("transfer_progress",""))
                    if marker.is_file():
                        r=json.loads(marker.read_text())
                        if 0<r["copied"]<r["total"]:reason="injected_"+state["inject"]
        if reason:
            write(out/"guard_trigger.json",dict(reason=reason,phase=state.get("phase"),at_epoch=time.time()))
            if mode=="local-rehearsal":
                # The controller need not lead its own process group. Kill its
                # validated PID first, so it cannot overwrite the guard receipt.
                if same(state["controller_pid"],state["controller_birth"]):
                    try:os.kill(state["controller_pid"],signal.SIGKILL)
                    except ProcessLookupError:pass
                for process in state.get("owned_children",[]):kill_owned(process)
                write(out/"termination.json",dict(verified=True,mode=mode,reason=reason,
                      provider="local mock; no provider API called",at_epoch=time.time()))
                return
            from vast_campaign_api import destroy_owned,owned_instance
            try:
                receipt=destroy_owned(state);write(out/"guard_destroy_receipt.json",receipt)
                if owned_instance(state) is None:
                    write(out/"termination.json",dict(verified=True,mode=mode,reason=reason,at_epoch=time.time()))
                    return
            except Exception as exc:
                write(out/"guard_retry.json",dict(error=type(exc).__name__,at_epoch=time.time()))
        time.sleep(.03 if mode=="local-rehearsal" else 2.)

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--directory",required=True);a=p.parse_args();main(a.directory)
