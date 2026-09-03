"""Deletion-gate formatter — pulled out of deletion-test.sh so the presentation
lives in Python, not in bash quote-escaping. `python -m quorum._gate NIGHT`
prints the with/without comparison and the verdict, exit 1 if the gate failed."""
import json, os, subprocess, sys

def _field(night, mode):
    py = os.environ.get('QUORUM_PY', sys.executable)
    return json.loads(subprocess.check_output([py, '-m', 'quorum', 'field', night, '--memory', mode]))

def _verdict(ci):
    if not ci: return 'no lean'
    if ci[0] > 0.5: return 'UP'
    if ci[1] < 0.5: return 'DOWN'
    return 'no lean'

def main(night):
    on = _field(night, 'on'); off = _field(night, 'off')
    print(f"\n════════ THE DELETION GATE · night {night} ════════")
    if on.get('status') != 'ok':
        print(f"  WITH memory:    {on.get('status')} — {on.get('reason','')}")
        print("  Nothing to compare. A night not in memory is CANNOT SAY, which is the gate working, not failing.")
        return 0
    e = on['evidenced']
    print(f"  WITH memory    (evidenced, warranted):  {e['n']} calls · {e['up_share']*100:.1f}% UP"
          + (f" · CI [{e['ci'][0]*100:.1f}, {e['ci'][1]*100:.1f}]" if e['ci'] else " · n<30, rate withheld"))
    print(f"  WITHOUT memory (naive vote, survives):  {off['n']} calls · {off['up_share']*100:.1f}% UP"
          + (f" · CI [{off['ci'][0]*100:.1f}, {off['ci'][1]*100:.1f}]" if off['ci'] else ""))
    von, voff = _verdict(e['ci']), _verdict(off['ci'])
    delta = abs(e['up_share'] - off['up_share']) * 100
    print(f"  verdict:        warranted={von}   naive={voff}")
    if delta < 1.0 and von == voff:
        print("  ❌ GATE FAILED — deleting memory changed nothing; the design is decoration.")
        return 1
    flip = "" if von == voff else f", and flips the verdict ({voff} → {von})"
    print(f"  ✅ GATE HELD — deleting memory moves the field {delta:.1f}pp{flip}.")
    print("════════════════════════════════════════════════")
    return 0

if __name__ == '__main__':
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else '2026-08-27'))
