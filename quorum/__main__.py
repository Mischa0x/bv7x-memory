"""``python -m quorum <cmd>`` — stdlib CLI over the memory.

  ingest  --from tests/fixtures/rows.json [--store PATH]   write records (idempotent)
  status  [--store PATH]                                   nights in memory, store size, tier
  field   NIGHT [--store PATH] [--memory on|off]           the field's belief for a night
  record  NIGHT RULE_ID [--store PATH]                     one decision record, reconstructed
  serve   [--port N] [--store PATH]                        the screen: the field explains itself
  attest  NIGHT [--store PATH]                              print the commitment for NIGHT (never broadcasts)
  verify  [--receipt PATH]                                 recompute the commitment and check it against attestation.json
  history NIGHT [--store PATH]                              tonight decomposed by each rule's engagement history
"""
import argparse, json, os, sys
from .record import QuorumMemory, DEFAULT_STORE, CANNOT_SAY


def main(argv=None):
    p = argparse.ArgumentParser(prog='quorum')
    sub = p.add_subparsers(dest='cmd', required=True)
    a = sub.add_parser('ingest'); a.add_argument('--from', dest='src', required=True); a.add_argument('--store', default=DEFAULT_STORE)
    a = sub.add_parser('status'); a.add_argument('--store', default=DEFAULT_STORE)
    a = sub.add_parser('field'); a.add_argument('night'); a.add_argument('--store', default=DEFAULT_STORE); a.add_argument('--memory', choices=['on', 'off'], default='on')
    a = sub.add_parser('record'); a.add_argument('night'); a.add_argument('rule'); a.add_argument('--store', default=DEFAULT_STORE)
    a = sub.add_parser('serve'); a.add_argument('--port', type=int, default=8420); a.add_argument('--store', default=DEFAULT_STORE)
    a = sub.add_parser('attest'); a.add_argument('night'); a.add_argument('--store', default=DEFAULT_STORE)
    a = sub.add_parser('verify'); a.add_argument('--receipt', default=None)
    a = sub.add_parser('history'); a.add_argument('night'); a.add_argument('--store', default=DEFAULT_STORE)
    args = p.parse_args(argv)

    if args.cmd == 'field' and args.memory == 'off':
        # Naive vote needs no memory — deliberately constructed without opening the store.
        src = os.path.join(os.path.dirname(__file__), '..', 'tests', 'fixtures', 'rows.json')
        D = json.load(open(src))
        dirs = [r[3] for r in D['rows'] if r[2] == args.night]
        print(json.dumps(QuorumMemory(None).field(args.night, memory=False, naive_directions=dirs), indent=1)); return 0

    if args.cmd == 'verify':
        # Needs no store, no key and no network — the point of the receipt.
        from .attest import verify, RECEIPT
        r = verify(args.receipt or RECEIPT)
        print(json.dumps(r, indent=1))
        return 0 if r['ok'] else 1

    if args.cmd == 'attest':
        # Prints. Never broadcasts — signing lives in tools/attest-base.mjs and
        # is an operator action, deliberately outside the judge-runnable path.
        from .attest import compute
        print(json.dumps(compute(args.night, args.store), indent=1))
        return 0

    if args.cmd == 'serve':
        from .server import serve
        return serve(args.port, args.store)

    if args.cmd in ('field', 'record', 'status', 'history') and not os.path.exists(args.store):
        # The deletion gate, honoured at the CLI: no store means CANNOT SAY, not an exception and not zeros.
        print(json.dumps({'status': CANNOT_SAY, 'reason': f'no memory store at {args.store}'}, indent=1)); return 2

    mem = QuorumMemory.open(args.store)
    if args.cmd == 'ingest':
        D = json.load(open(args.src))
        print(json.dumps(mem.ingest(D['predicates'], D['snapshots'], D['rows'])))
    elif args.cmd == 'status':
        st = mem.m.free_tier_status()
        print(json.dumps({'store': args.store, 'nights': mem.nights(), 'rules': len(mem._rules()),
                          'db_mb': round(st['db_size_bytes'] / 1e6, 2), 'cap_pct': round(100 * st['pct_used'], 1), 'tier': st['tier']}, indent=1))
    elif args.cmd == 'field':
        print(json.dumps(mem.field(args.night, memory=True), indent=1))
    elif args.cmd == 'history':
        from .server import field_on
        print(json.dumps(field_on(args.night, args.store).get('history'), indent=1))
    elif args.cmd == 'record':
        r = mem.record(args.night, args.rule)
        print(json.dumps(r if r is not None else {'status': CANNOT_SAY, 'reason': 'night or rule not in memory'}, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
