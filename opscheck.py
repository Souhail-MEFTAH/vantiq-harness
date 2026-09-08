"""What a namespace costs when nobody is watching it.

The single largest operational surprise across these demos was not a bug, it was
arithmetic. A browser tab left open on a dashboard generated roughly 130,000
procedure calls a day. Schedulers ran whether or not the demo was running. A
scheduled procedure fires once per cluster node, so an estimate made on one node
was a third of the truth. None of that shows up as an error anywhere.

This measures the three things that can actually be measured, and refuses to
guess at the rest:

  1. what one poll cycle of a screen costs, in calls, bytes and milliseconds
  2. what that extrapolates to over a day if the tab is left open
  3. what is scheduled to run regardless of whether anyone is present

Everything here is a MEASUREMENT with its method stated, not a projection with a
confident number. A projection labelled as a measurement is how a credible demo
produces an incredible figure.
"""
import json
import sys
import time

from client import Client, VantiqError


WARMUPS = 3


def time_call(client, fqn, params=None, repeats=5):
    """Median wall time and payload size, after real warm-up.

    The first calls of a run are cold start. One read model measured 923ms cold
    and 140ms warm, and the cold number was briefly taken as evidence that the
    backend was slow. It was not: the client was painting a blank panel while it
    waited.

    This tool fell for the same thing on its first run. One warm-up call and a
    median of three reported getRunState at 1630ms, six times the next slowest
    read model, which read as a regression that did not exist. Three warm-ups
    and a median of five put it at 108ms, in line with everything else. A
    measurement tool that is fooled by cold start will manufacture regressions,
    which is worse than not measuring.
    """
    for _ in range(WARMUPS):
        try:
            client.execute(fqn, params)
        except VantiqError:
            return None
    times, size = [], 0
    for _ in range(repeats):
        t0 = time.time()
        try:
            body = client.execute(fqn, params)
        except VantiqError:
            return None
        times.append((time.time() - t0) * 1000.0)
        size = len(json.dumps(body)) if body is not None else 0
    times.sort()
    return {"ms": times[len(times) // 2], "bytes": size}


def poll_cost(client, package, read_models, poll_seconds=4.0, nodes=1):
    """One screen's poll cycle, and the day it implies.

    `nodes` exists because a scheduled procedure fires once per cluster node.
    An estimate that assumes one node was three times low on a three-node
    cluster, and the correction changed which lever was worth pulling.
    """
    rows, total_ms, total_bytes = [], 0.0, 0
    for name in read_models:
        fqn = "%s.%s" % (package, name)
        r = time_call(client, fqn)
        if r is None:
            rows.append((name, None, None))
            continue
        rows.append((name, r["ms"], r["bytes"]))
        total_ms += r["ms"]
        total_bytes += r["bytes"]
    cycles_per_day = 86400.0 / poll_seconds
    return {
        "rows": rows,
        "calls_per_cycle": len(read_models),
        "ms_per_cycle": total_ms,
        "bytes_per_cycle": total_bytes,
        "calls_per_day": cycles_per_day * len(read_models) * nodes,
        "mb_per_day": cycles_per_day * total_bytes * nodes / 1e6,
        "poll_seconds": poll_seconds,
        "nodes": nodes,
    }


def scheduled(client):
    """What runs whether or not anyone is present.

    Note the resource name: `scheduledevents`, not `system.scheduledevents`.
    The latter is a 500, because the server prefixes `system.` itself.
    """
    try:
        rows = client.select("scheduledevents", limit=200)
    except VantiqError as exc:
        return None, str(exc)[:160]
    out = []
    for r in rows:
        interval = r.get("interval")
        out.append({
            "name": r.get("name"),
            # interval is MILLISECONDS. Read as seconds it looks like an hourly
            # job that is in fact firing every few seconds.
            "interval_ms": interval,
            "per_day": (86400000.0 / interval) if interval else None,
            "active": r.get("isActive", r.get("active")),
            "topic": r.get("topic"),
            "faults": scheduled_faults(r),
        })
    return out, None


def scheduled_faults(row):
    """Everything wrong with one scheduledevents record, as a list of strings.

    Four separate entries from the pooled learnings, all on the same resource,
    and every one of them fails in a way that leaves the event LOOKING fine.

      NR-38, verified live on dev.vantiq.com. The create body is
      `{name, active, periodic, interval, topic, message}`. Missing target:
      `400 io.vantiq.scheduledEvent.required.properties - "must specify either a
      topic or a resource"`. Sub-second interval:
      `400 io.vantiq.scheduledEvent.interval.positive`.

      PS-14. The target must be a user-defined TOPIC. Pointing it at a service
      event path is rejected on save - the brief's first choice
      `/services/demo.eda.SimulatorService/tickRequest` came back "not a valid
      user defined topic" - and the fallback costs three extra steps: create a
      plain `topics` resource, subscribe the rule via `/topics/<path>`, and
      remove the now-unused INBOUND event type.

      PS-16. This is the one that wastes an afternoon, because nothing is
      broken: a scheduled event PUBLISHES ITS MESSAGE TO ITS TOPIC and cannot
      call a procedure. There is no `ruleToFire` field. Something else has to
      react, so every scheduled event needs a rule on
      `WHEN EVENT OCCURS ON "/topics/<path>"` or it is a no-op that reports
      healthy. `dead_schedules()` below is the check for that.
    """
    faults = []
    interval = row.get("interval")
    topic = row.get("topic")
    if not topic and not row.get("resource"):
        faults.append("no topic and no resource: the create is rejected with "
                      "io.vantiq.scheduledEvent.required.properties")
    if interval is None:
        faults.append("no interval")
    elif interval < 1000:
        faults.append("interval %sms is below the 1000ms floor "
                      "(io.vantiq.scheduledEvent.interval.positive); note the "
                      "unit is MILLISECONDS" % interval)
    if topic and topic.startswith("/services/"):
        faults.append("topic `%s` is a service-event path, not a user-defined "
                      "topic; this is rejected on save. Publish to a plain "
                      "`topics` resource and subscribe the rule to "
                      "/topics/<path>." % topic)
    return faults


SERVICE_SCHEDULE_MINIMUM_MS = 60000


def service_schedule_faults(rows):
    """Service-Builder scheduled procedures have a 60,000ms grid. PS-15.

    A standalone `scheduledevents` resource does NOT share this constraint -
    5,000ms and 10,000ms intervals ran in the same namespace - so the two look
    interchangeable and are not:

        {"code":"io.vantiq.service.scheduled.invalid.interval.multiple",
         "message":"The interval (15,000 ms) for the procedure
         com.vantiq.ps.wildfire.EscalationService.ActiveCollabsWriteAll is not
         an even multiple of the minimum scheduling interval (60,000 ms)."}

    `rows` is whatever the caller has that carries a `name` and an `interval`.
    Returns [(name, message)].
    """
    out = []
    for r in rows or []:
        interval = r.get("interval")
        if interval is None:
            continue
        if interval % SERVICE_SCHEDULE_MINIMUM_MS:
            out.append((r.get("name"),
                        "interval %sms is not an even multiple of the %sms "
                        "minimum for a SERVICE scheduled procedure. Use a "
                        "multiple, or move the cadence to a standalone "
                        "scheduled event -> topic -> rule, which has no such "
                        "constraint." % (interval, SERVICE_SCHEDULE_MINIMUM_MS)))
    return out


def dead_schedules(client, events):
    """Scheduled events whose topic nothing subscribes to. PS-16.

    A scheduled event only publishes its `message` to its `topic`; it cannot
    invoke a procedure. With no rule listening, it fires forever, costs what
    note 40 says it costs once per cluster node, and does nothing at all. The
    record itself reads healthy, which is why this needs a cross-check rather
    than an inspection.

    Returns ([(name, topic)], error). The error is not fatal: a namespace whose
    rules are not readable simply gets no answer here, which is better than a
    confident empty list.
    """
    try:
        rules = client.select("rules", limit=500, props=["name", "ruleText"])
    except VantiqError as exc:
        return [], str(exc)[:160]
    # `ruleText` is the field a rule's body lives in. NR-38: sending `source` on
    # a rule create is a server-side NullPointerException, and the server stores
    # what you send as ruleText INTO source, so reading either can be right
    # depending on the version. Both are checked rather than guessed.
    bodies = " ".join((r.get("ruleText") or r.get("source") or "") for r in rules)
    out = []
    for e in events or []:
        topic = e.get("topic")
        if not topic or topic.startswith("/services/"):
            continue
        if topic.strip("/") not in bodies:
            out.append((e.get("name"), topic))
    return out, None


def report(repo, package, read_models, poll_seconds=4.0, nodes=1):
    client = Client(repo=repo)
    print("ops check: %s on %s" % (package, client.server))

    print("\nread models, warmed, median of 3")
    cost = poll_cost(client, package, read_models, poll_seconds, nodes)
    for name, ms, size in cost["rows"]:
        if ms is None:
            print("  %-28s could not be called" % name)
        else:
            print("  %-28s %7.0f ms  %8d B" % (name, ms, size))
    print("  %-28s %7.0f ms  %8d B  per cycle"
          % ("TOTAL", cost["ms_per_cycle"], cost["bytes_per_cycle"]))

    print("\nan idle tab, polling every %.0fs on %d node(s)"
          % (cost["poll_seconds"], cost["nodes"]))
    print("  %-28s %s" % ("procedure calls per day", "{:,.0f}".format(cost["calls_per_day"])))
    print("  %-28s %.1f MB" % ("payload per day", cost["mb_per_day"]))
    print("  measured, not projected: cycle cost times cycles per day. It assumes")
    print("  the tab stays open and the screen keeps asking, which is what happens.")

    events, err = scheduled(client)
    print("\nscheduled to run whether or not anyone is present")
    if err:
        print("  could not read scheduledevents: %s" % err)
    elif not events:
        print("  none in this namespace")
    else:
        for e in events:
            per = ("{:,.0f}/day".format(e["per_day"] * nodes)) if e["per_day"] else "?"
            print("  %-34s every %-9s %s  active=%s"
                  % (e["name"], "%sms" % e["interval_ms"], per, e["active"]))
            for fault in e["faults"]:
                print("      ! %s" % fault)
        print("  interval is MILLISECONDS, and each fires once PER CLUSTER NODE.")

        dead, derr = dead_schedules(client, events)
        if derr:
            print("  could not cross-check subscribers: %s" % derr)
        elif dead:
            print("\n  firing into a topic nothing subscribes to:")
            for name, topic in dead:
                print("      %-30s -> %s" % (name, topic))
            print("  a scheduled event publishes its message to its topic; it")
            print("  cannot call a procedure. With no rule on the topic it costs")
            print("  what the line above says and does nothing.")
    return cost


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("usage: opscheck.py <repo> <package> [ReadModel ...]")
        raise SystemExit(2)
    report(sys.argv[1], sys.argv[2], sys.argv[3:] or ["ApiGateway.getRunState"])
