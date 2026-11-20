#!/usr/bin/env python3
"""
Build an esmini scenario (OpenSCENARIO 1.1 + OpenDRIVE) reconstructing
CIREN case 189 (NHTSA case 3-C1-2018-032): a 2013 Ford F-150 crew cab whose
driver fell asleep on a right-hand curve, drifted off the left side of the
road and hit a concrete overpass support with the left front corner.

Input:  the CIREN case export workbook (CrashExport-189-*.xlsx)
Writes: ciren_case189.xodr, ciren_case189.xosc

    python ciren_case189.py CrashExport-189-11-20-2026.xlsx

Put both outputs in esmini/resources/xosc/ and run from esmini/run/esmini:
    ..\\..\\bin\\esmini.exe --window 60 60 1280 720 --trail_mode 1 --osc ..\\..\\resources\\xosc\\ciren_case189.xosc

FROM THE CASE EXPORT
  - EDR (EDRPRECRASH): speed, accelerator, brake and steering-wheel angle for
    the 5 s before impact. 77 km/h, foot coming off the throttle, no braking,
    a steady ~8 deg right steering input, then a sharp right input (-68 deg)
    in the last 0.3 s (the driver may have woken up)
  - Road (GV): 1 northbound lane, curve right, level, dry asphalt, divided
    with a positive barrier, 72 km/h (45 mph) limit, no traffic controls
  - Vehicle (VEHSPEC): length 6.11 m, width 2.00 m, wheelbase 3.98 m,
    front/rear overhang 0.98 / 1.16 m, curb weight 2454 kg
  - Impact (CDC 12FLAW06): front, left, direct damage centred 0.91 m left of
    the vehicle centreline; object = concrete overpass support (>=1.2 m wide)
  - Rest: rotated counter-clockwise, across the northbound lane, facing NW

ASSUMED (edit the constants below)
  - steering ratio 20:1 and a simple kinematic (bicycle) model, no understeer
  - the truck starts 5 s before impact centred in its lane
  - left shoulder 1.2 m, right shoulder 3.1 m, lane 3.6 m
  - the curve radius is SOLVED so that the EDR-driven path reaches the support
    at the moment of impact (printed when you run the script)
  - post-impact rotation and rest position are approximate
"""

import bisect
import math
import sys
from xml.sax.saxutils import quoteattr

# ---------------------------------------------------------------- constants
OUT_XODR = "ciren_case189.xodr"
OUT_XOSC = "ciren_case189.xosc"

STEER_RATIO = 20.0        # steering wheel deg per road-wheel deg (assumed)
LANE_W = 3.6
SHOULDER_L = 1.2          # between lane edge line and the support (assumed)
SHOULDER_R = 3.1
MEDIAN_W = 8.0            # gore between this roadway and the next (assumed)
PIER = dict(W=1.2, L=1.2, H=6.0)   # concrete overpass support
PIER_Y = SHOULDER_L + PIER["W"] / 2   # pier centre, metres left of lane edge

T_PRE = 5.0               # EDR covers 5 s before impact; sim t = EDR t + T_PRE
T_REST = T_PRE + 1.2
T_END = T_PRE + 3.0
DT = 0.01                 # integration step
OUT_DT = 0.05             # trajectory vertex spacing
S_START = 40.0            # where along the road the truck starts

TRUCK = dict(name="V1_Ford_F150_2013", model="car_red",
             L=6.11, W=2.00, H=1.96, WB=3.98, OHF=0.98, OHR=1.16)
CONTACT_Y = 0.91          # direct damage centre, m left of truck centreline
REST_YAW_COMPASS = 315.0  # facing NW


# ---------------------------------------------------------------- EDR input
def read_edr(xlsx):
    import openpyxl
    wb = openpyxl.load_workbook(xlsx, read_only=True)
    rows = list(wb["EDRPRECRASH"].iter_rows(values_only=True))
    h = rows[0]
    speed, steer, accel, brake = [], [], [], []
    for r in rows[1:]:
        d = dict(zip(h, r))
        name, t = d["PCODETEXT"], float(d["PTIME"])
        val = d["PVALUETEXT"]
        if name.startswith("Vehicle Speed"):
            speed.append((t, float(val) / 3.6))
        elif name.startswith("Steering input"):
            steer.append((t, float(val)))
        elif name.startswith("Accelerator"):
            accel.append((t, float(val)))
        elif name.startswith("Service Brake"):
            brake.append((t, val))
    case = dict(zip(*[list(x) for x in list(wb["CRASH"].iter_rows(values_only=True))[:2]]))
    return sorted(speed), sorted(steer), sorted(accel), sorted(brake), case


def interp(series, t):
    ts = [p[0] for p in series]
    if t <= ts[0]:
        return series[0][1]
    if t >= ts[-1]:
        return series[-1][1]
    i = bisect.bisect_right(ts, t) - 1
    (t0, v0), (t1, v1) = series[i], series[i + 1]
    return v0 + (v1 - v0) * (t - t0) / (t1 - t0)


# ---------------------------------------------------------------- road geometry
class Road:
    """Arc of constant curvature (right turn), reference line = left edge of
    the northbound lane. Heading chosen so the road points due north at the
    impact location."""

    def __init__(self, R, s_north):
        self.k = -1.0 / R
        self.h0 = math.pi / 2 - self.k * s_north

    def pose(self, s):
        k, h0 = self.k, self.h0
        x = (math.sin(h0 + k * s) - math.sin(h0)) / k
        y = (math.cos(h0) - math.cos(h0 + k * s)) / k
        return x, y, h0 + k * s

    def to_frenet(self, x, y):
        """s, t (t positive to the left) by Newton iteration"""
        s = 0.0
        for _ in range(60):
            px, py, ph = self.pose(s)
            ds = (x - px) * math.cos(ph) + (y - py) * math.sin(ph)
            s += ds
            if abs(ds) < 1e-7:
                break
        px, py, ph = self.pose(s)
        t = -(x - px) * math.sin(ph) + (y - py) * math.cos(ph)
        return s, t


def drive(road, speed, steer):
    """Kinematic bicycle driven by EDR speed and steering. Reference point =
    rear axle. Returns [(sim_t, x, y, yaw)] from EDR -5 s to 0 s."""
    x, y, h = road.pose(S_START)
    # start centred in the lane: lane centre is LANE_W/2 right of reference line
    x += LANE_W / 2 * math.sin(h)
    y -= LANE_W / 2 * math.cos(h)
    # rear axle sits behind the vehicle centre
    c_off = (TRUCK["WB"] + TRUCK["OHF"] - TRUCK["OHR"]) / 2
    x -= c_off * math.cos(h)
    y -= c_off * math.sin(h)
    pts, t = [], -T_PRE
    while t <= 1e-9:
        pts.append((round(t + T_PRE, 4), x, y, h))
        v = interp(speed, t)
        delta = math.radians(interp(steer, t) / STEER_RATIO)
        x += v * math.cos(h) * DT
        y += v * math.sin(h) * DT
        h += v * math.tan(delta) / TRUCK["WB"] * DT
        t = round(t + DT, 6)
    return pts


def contact_point(p):
    _, x, y, h = p
    fx = TRUCK["WB"] + TRUCK["OHF"]          # front bumper ahead of rear axle
    return (x + fx * math.cos(h) - CONTACT_Y * math.sin(h),
            y + fx * math.sin(h) + CONTACT_Y * math.cos(h))


def solve(speed, steer):
    """Find R so the contact point's lateral offset at impact = pier centre."""
    def miss(R):
        road = Road(R, S_START + 110)
        pts = drive(road, speed, steer)
        cx, cy = contact_point(pts[-1])
        s, t = road.to_frenet(cx, cy)
        return t - PIER_Y, road, pts, s
    lo, hi = 150.0, 5000.0          # tighter curve -> truck ends further left
    for _ in range(80):
        mid = math.sqrt(lo * hi)
        if miss(mid)[0] > 0:      # ends too far left: curve too tight
            lo = mid
        else:
            hi = mid
    R = math.sqrt(lo * hi)
    # re-centre the road so it points north at the impact location
    _, road0, pts0, s_imp = miss(R)
    road = Road(R, s_imp)
    pts = drive(road, speed, steer)
    cx, cy = contact_point(pts[-1])
    s_imp, t_imp = road.to_frenet(cx, cy)
    return R, road, pts, s_imp, t_imp


def post_impact(p_imp, road, s_imp):
    """Front stays near the support, truck spins counter-clockwise to face NW,
    rear swings right across the northbound lane."""
    t0, x0, y0, h0 = p_imp
    fx = TRUCK["WB"] + TRUCK["OHF"]
    front0 = (x0 + fx * math.cos(h0), y0 + fx * math.sin(h0))
    _, _, hr = road.pose(s_imp)
    rest_h = math.radians(90.0 + (360.0 - REST_YAW_COMPASS))   # NW = 135 deg
    while rest_h - h0 > math.pi:
        rest_h -= 2 * math.pi
    while rest_h - h0 < -math.pi:
        rest_h += 2 * math.pi
    # front backs off 0.6 m and slides 0.5 m right of where it hit
    front1 = (front0[0] - 0.6 * math.cos(hr) + 0.5 * math.sin(hr),
              front0[1] - 0.6 * math.sin(hr) - 0.5 * math.cos(hr))
    out, t = [], t0 + OUT_DT
    while t <= T_REST + 1e-9:
        f = (t - t0) / (T_REST - t0)
        e = 1 - (1 - f) ** 3
        h = h0 + (rest_h - h0) * e
        fxp = front0[0] + (front1[0] - front0[0]) * e
        fyp = front0[1] + (front1[1] - front0[1]) * e
        out.append((round(t, 4), fxp - fx * math.cos(h), fyp - fx * math.sin(h), h))
        t = round(t + OUT_DT, 6)
    last = out[-1]
    out.append((T_END, last[1], last[2], last[3]))
    return out


# ---------------------------------------------------------------- writers
def f3(v):
    return f"{v:.3f}"


def xodr(road, length):
    def lane(lid, ltype, width, mark):
        rm = ""
        if mark:
            mtype, color = mark
            rm = (f'<roadMark sOffset="0" type="{mtype}" weight="standard" color="{color}" '
                  f'width="0.15" laneChange="none"/>')
        w = f'<width sOffset="0" a="{width}" b="0" c="0" d="0"/>' if lid != 0 else ""
        return f'<lane id="{lid}" type="{ltype}" level="false"><link/>{w}{rm}</lane>'

    x0, y0, h0 = road.pose(0)
    left = (lane(4, "shoulder", 1.0, None) +
            lane(3, "driving", LANE_W, ("solid", "standard")) +
            lane(2, "median", MEDIAN_W, None) +
            lane(1, "shoulder", SHOULDER_L, None))
    center = lane(0, "none", 0, ("solid", "yellow"))
    right = (lane(-1, "driving", LANE_W, ("solid", "standard")) +
             lane(-2, "shoulder", SHOULDER_R, None))
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<OpenDRIVE>
  <header revMajor="1" revMinor="6" name="CIREN case 189 road" version="1.0" date="2026-11-20"
          north="0" south="0" east="0" west="0"/>
  <!-- Right-hand curve, R = {1 / -road.k:.0f} m (solved from the EDR path).
       Reference line = left edge of the northbound lane. x = east, y = north. -->
  <road name="NB_ramp" length="{length:.3f}" id="1" junction="-1">
    <link/>
    <type s="0" type="rural"><speed max="72" unit="km/h"/></type>
    <planView>
      <geometry s="0" x="{x0:.4f}" y="{y0:.4f}" hdg="{h0:.6f}" length="{length:.3f}"><arc curvature="{road.k:.8f}"/></geometry>
    </planView>
    <elevationProfile><elevation s="0" a="0" b="0" c="0" d="0"/></elevationProfile>
    <lateralProfile/>
    <lanes>
      <laneSection s="0">
        <left>{left}</left>
        <center>{center}</center>
        <right>{right}</right>
      </laneSection>
    </lanes>
  </road>
</OpenDRIVE>
'''


def time_trigger(name, t):
    return (f'<StartTrigger><ConditionGroup><Condition name="{name}" delay="0" conditionEdge="none">'
            f'<ByValueCondition><SimulationTimeCondition value="{f3(t)}" rule="greaterOrEqual"/>'
            f'</ByValueCondition></Condition></ConditionGroup></StartTrigger>')


def xosc(pts, pier_pose, R, case_summary):
    T = TRUCK
    cx = (T["WB"] + T["OHF"] - T["OHR"]) / 2
    verts = "\n".join(
        f'            <Vertex time="{f3(t)}"><Position><WorldPosition x="{f3(x)}" y="{f3(y)}" h="{h:.4f}"/></Position></Vertex>'
        for (t, x, y, h) in pts)
    px, py, ph = pier_pose
    p0 = pts[0]
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<!--
  CIREN case 189 (NHTSA 3-C1-2018-032) reconstruction for esmini.
  2013 Ford F-150 crew cab, northbound on a right-hand curve at 77 km/h.
  Driver asleep: no braking, steering too gentle for the curve, so the truck
  drifts off the left side and hits a concrete overpass support with the
  left front corner. Path driven by the EDR speed and steering record.

  Timeline (s): 0.0 = EDR -5 s | 4.7 sharp right steer (driver wakes?)
                {T_PRE:.1f} impact at ~76 km/h | {T_REST:.1f} at rest facing NW | {T_END:.1f} end
  Curve radius {R:.0f} m was solved so the EDR path reaches the support.
  Assumptions are listed in ciren_case189.py.  x = east, y = north.
-->
<OpenSCENARIO>
  <FileHeader revMajor="1" revMinor="1" date="2026-11-20T00:00:00"
              description="CIREN case 189 run-off-road into bridge support" author="Marco Walther"/>
  <ParameterDeclarations>
    <ParameterDeclaration name="Impacted" parameterType="boolean" value="false"/>
  </ParameterDeclarations>
  <CatalogLocations/>
  <RoadNetwork>
    <LogicFile filepath="{OUT_XODR}"/>
  </RoadNetwork>
  <Entities>
    <ScenarioObject name="{T['name']}"><Vehicle name="{T['name']}" vehicleCategory="car" model3d="../models/{T['model']}.osgb"><ParameterDeclarations/>
      <BoundingBox><Center x="{f3(cx)}" y="0" z="{f3(T['H'] / 2)}"/><Dimensions width="{T['W']}" length="{T['L']}" height="{T['H']}"/></BoundingBox>
      <Performance maxSpeed="50" maxAcceleration="10" maxDeceleration="12"/>
      <Axles><FrontAxle maxSteering="0.6" wheelDiameter="0.78" trackWidth="1.70" positionX="{T['WB']}" positionZ="0.39"/>
      <RearAxle maxSteering="0" wheelDiameter="0.78" trackWidth="1.70" positionX="0" positionZ="0.39"/></Axles>
      <Properties><Property name="scaleMode" value="ModelToBB"/></Properties></Vehicle></ScenarioObject>
    <ScenarioObject name="Overpass_Support"><MiscObject name="Overpass_Support" miscObjectCategory="obstacle" mass="100000" model3d="../models/box_cc_by.osgb"><ParameterDeclarations/>
      <BoundingBox><Center x="0" y="0" z="{f3(PIER['H'] / 2)}"/><Dimensions width="{PIER['W']}" length="{PIER['L']}" height="{PIER['H']}"/></BoundingBox>
      <Properties><Property name="scaleMode" value="ModelToBB"/></Properties></MiscObject></ScenarioObject>
  </Entities>
  <Storyboard>
    <Init><Actions>
      <Private entityRef="{T['name']}"><PrivateAction><TeleportAction><Position>
        <WorldPosition x="{f3(p0[1])}" y="{f3(p0[2])}" h="{p0[3]:.4f}"/></Position></TeleportAction></PrivateAction></Private>
      <Private entityRef="Overpass_Support"><PrivateAction><TeleportAction><Position>
        <WorldPosition x="{f3(px)}" y="{f3(py)}" h="{ph:.4f}"/></Position></TeleportAction></PrivateAction></Private>
    </Actions></Init>
    <Story name="Case189">
      <Act name="Crash">
      <ManeuverGroup name="Truck_mg" maximumExecutionCount="1">
        <Actors selectTriggeringEntities="false"><EntityRef entityRef="{T['name']}"/></Actors>
        <Maneuver name="EDR_driven_path">
          <Event name="Drive" priority="overwrite">
            <Action name="Follow_EDR_path">
              <PrivateAction><RoutingAction><FollowTrajectoryAction>
                <TrajectoryRef><Trajectory name="Truck_path" closed="false"><Shape><Polyline>
{verts}
                </Polyline></Shape></Trajectory></TrajectoryRef>
                <TimeReference><Timing domainAbsoluteRelative="absolute" scale="1" offset="0"/></TimeReference>
                <TrajectoryFollowingMode followingMode="position"/>
              </FollowTrajectoryAction></RoutingAction></PrivateAction>
            </Action>
            {time_trigger("drive_start", 0)}
          </Event>
          <!-- Fires (and is logged) when the truck touches the support -->
          <Event name="Impact" priority="parallel">
            <Action name="RecordImpact">
              <GlobalAction><ParameterAction parameterRef="Impacted"><SetAction value="true"/></ParameterAction></GlobalAction>
            </Action>
            <StartTrigger><ConditionGroup>
              <Condition name="Truck_hits_support" delay="0" conditionEdge="rising"><ByEntityCondition>
                <TriggeringEntities triggeringEntitiesRule="any"><EntityRef entityRef="{T['name']}"/></TriggeringEntities>
                <EntityCondition><CollisionCondition><EntityRef entityRef="Overpass_Support"/></CollisionCondition></EntityCondition>
              </ByEntityCondition></Condition>
            </ConditionGroup></StartTrigger>
          </Event>
        </Maneuver>
      </ManeuverGroup>
        {time_trigger("act_start", 0)}
      </Act>
    </Story>
    <StopTrigger><ConditionGroup><Condition name="end" delay="0" conditionEdge="rising">
      <ByValueCondition><SimulationTimeCondition value="{f3(T_END)}" rule="greaterThan"/></ByValueCondition>
    </Condition></ConditionGroup></StopTrigger>
  </Storyboard>
</OpenSCENARIO>
'''


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("usage: python ciren_case189.py <CrashExport-189-....xlsx>")
    speed, steer, accel, brake, case = read_edr(sys.argv[1])
    R, road, pts, s_imp, t_imp = solve(speed, steer)
    # pier: its near face sits on the contact point (5 cm overlap so the
    # collision check fires), aligned with the road
    cx, cy = contact_point(pts[-1])
    _, _, hr = road.pose(s_imp)
    d = PIER["L"] / 2 - 0.05
    pier = (cx + d * math.cos(hr), cy + d * math.sin(hr), hr)
    # thin the EDR path to OUT_DT and add the post-impact motion
    path = [p for p in pts if abs(p[0] / OUT_DT - round(p[0] / OUT_DT)) < 1e-6]
    path += post_impact(pts[-1], road, s_imp)
    length = s_imp + 120.0
    with open(OUT_XODR, "w", encoding="utf-8") as f:
        f.write(xodr(road, length))
    with open(OUT_XOSC, "w", encoding="utf-8") as f:
        f.write(xosc(path, pier, R, case.get("SUMMARY", "")))
    s0, t0 = road.to_frenet(*contact_point(pts[0]))
    print(f"solved curve radius R = {R:.0f} m")
    print(f"impact at s = {s_imp:.1f} m, contact {t_imp:.2f} m left of lane edge "
          f"(pier centre {PIER_Y:.2f} m), speed {interp(speed, 0) * 3.6:.1f} km/h")
    print(f"truck heading vs road at impact: {math.degrees(pts[-1][3] - hr):.1f} deg (left)")
