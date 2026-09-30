# `hud/` — the cockpit

Eyes move the reticle, hands select and stop things, the keyboard is the only signature
in the building.

```bash
# live, with the bridge running
uvicorn jarvis.server:app --host 127.0.0.1 --port 8765
open http://127.0.0.1:8765/

# offline, no agent and no camera needed
open hud/index.html
```

Opened from disk it falls back to the graph snapshot embedded in the page, reports the
bridge as `offline` rather than pretending, and still works on mouse and keyboard.

## Controls

| Input | Does | Why it is safe |
|---|---|---|
| Gaze dwell, 350 ms | Targets a node and opens its contract | Highlighting changes nothing |
| Pinch | Selects the targeted node | Selection is read only |
| Pinch drag | Pans the map | Navigation |
| Two hands apart | Zooms | Navigation |
| Palm out, 400 ms | HALT: rejects the open gate | It can only ever stop things |
| Fist, 1 s | Kill switch: rejects every gate, drops the socket | Same direction, longer hold |
| **Typing** | **The only way to approve anything** | A camera cannot forge a keystroke |

Gaze is a good pointer and a terrible click, so the commit is always a different muscle.
Two independent modalities have to agree before anything opens, and a third before
anything changes.

## The gate strip

Deliberately ugly and deliberately slow. It shows the tool name and the full argument
JSON, never a summary: if an email is going out, you read the body. For a `device` or
`external` call the approval phrase includes a four digit code generated at that moment
and shown on screen, so muscle memory and a replayed message both fail. Palm out, Escape
and closing the window all reject. Three minutes of silence rejects.

## Reading the map

Ring colour is status: green live, gold wired, grey planned, red denied. The number
inside a cluster ring counts what is accumulating there. A hexagon is a connector, a
door to something outside. A small gold pip means the tool will stop and ask. The
`gates` tab lists everything capable of changing the world, which is the tab worth
reading out loud once a week.

## First run

Click **start tracking** and grant the camera; hands work immediately. Then
**calibrate gaze**: nine dots, about fifteen seconds. Expect roughly 3 to 5 degrees of
accuracy from a webcam, which is a cluster rather than a button, so targets are large on
purpose. Recalibrate when you change posture or lighting. A lamp behind the monitor
aimed at your face is worth more than any filter.

`simulate gate` opens the confirm strip with no agent running, if you just want to see it.
