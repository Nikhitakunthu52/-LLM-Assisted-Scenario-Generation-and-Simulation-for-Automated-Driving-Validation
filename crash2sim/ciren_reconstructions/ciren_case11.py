#!/usr/bin/env python3
"""
Build an esmini scenario (OpenSCENARIO 1.1 + OpenDRIVE) reconstructing
CIREN case 11 (NHTSA case 3-C4-2017-002): head-on collision between a
2014 Ford Focus (V1, case vehicle) and a 2010 Honda Civic (V2).

Writes:
    ciren_case11.xodr   straight 3-lane road (1 eastbound, 2 westbound)
    ciren_case11.xosc   the scenario

Put both files in esmini/resources/xosc/ and run from esmini/run/esmini:
    ..\\..\\bin\\esmini.exe --window 60 60 1280 720 --trail_mode 1 --osc ..\\..\\resources\\xosc\\ciren_case11.xosc

Values taken from the case (crashviewer.nhtsa.dot.gov/ciren/details/11):
  - straight, not divided, 3 lanes: 1 eastbound, 2 westbound; double solid yellow
    centre line; dashed white between westbound lanes; paved shoulders
  - speed limit 80 km/h (55 mph); westbound +4% grade
  - V1 westbound in the far-left (inner) westbound lane, inattentive, drifted
    left across the centre line, then braked and steered right
  - V2 eastbound, saw V1 encroaching, braked and steered left
  - front-to-front impact; heading at impact V1 275 deg, V2 80 deg (compass)
  - V1 delta-V 52 km/h (SMASH, flagged "results appear low")
  - after impact V1 rotated clockwise to rest facing NW, V2 counter-clockwise
    to rest facing NE, both straddling the centre line
  - V1 curb weight 1340 kg

ASSUMED (not in the case data; edit the constants below):
  - both vehicles travelling at the 80 km/h limit before the event
  - drift timing, braking of 0.7 g starting ~1 s before impact
  - impact speeds ~55 km/h each, chosen so the closing speed (~108 km/h) is
    consistent with V1's 52 km/h delta-V for two similar-mass cars
  - post-impact paths and rest positions are approximate
"""

import math
from xml.sax.saxutils import quoteattr

# ---------------------------------------------------------------- constants
OUT_XODR = "ciren_case11.xodr"
OUT_XOSC = "ciren_case11.xosc"

ROAD_LEN = 560.0          # m, road runs along +x; +x = WEST (real world)
LANE_W = 3.6
SHOULDER_W = 2.4
GRADE = 0.04              # uphill in +x (westbound), so eastbound is downhill

G = 9.81
V0 = 80 / 3.6             # both vehicles at the 80 km/h limit (assumed)
BRAKE = 0.7 * G           # hard braking (assumed)
DT = 0.05                 # trajectory sample step, s

T_DRIFT_START = 3.5       # V1 starts drifting left (inattentive)
T_DRIFT_END = 7.9         # V1 peak encroachment
T_V1_REACT = 8.0          # V1 notices: brakes + steers right
T_V2_REACT = 7.9          # V2 notices: brakes + steers left
T_IMPACT = 9.0
T_REST = 10.5
T_END = 12.5

IMPACT_X = 280.0          # where along the road the impact happens

# compass heading (deg) -> yaw in this frame (+x = west, +y = south)
def yaw_from_compass(h_deg):
    return math.radians(270.0 - h_deg)

V1_IMPACT_YAW = yaw_from_compass(275)   # -5 deg: steering back right (north)
V2_IMPACT_YAW = yaw_from_compass(80)    # 190 deg: steering left (north)
V1_REST_YAW = yaw_from_compass(315)     # facing NW
V2_REST_YAW = yaw_from_compass(45)      # facing NE

V1 = dict(name="V1_Ford_Focus_2014", model="car_red", L=4.54, W=1.82, H=1.47)
V2 = dict(name="V2_Honda_Civic_2010", model="car_blue", L=4.50, W=1.75, H=1.43)

# lane centres (y): westbound lanes are on the right of +x, i.e. negative y
Y_WB_INNER = -LANE_W / 2          # lane -1, "far left" westbound lane
Y_EB = +LANE_W / 2                # lane +1, the single eastbound lane


def smooth(a, b, t, t0, t1):
    """cosine blend from a (t<=t0) to b (t>=t1)"""
    if t <= t0:
        return a
    if t >= t1:
        return b
    f = 0.5 - 0.5 * math.cos(math.pi * (t - t0) / (t1 - t0))
    return a + (b - a) * f


# ---------------------------------------------------------------- kinematics
def speed_v1(t):
    if t < T_V1_REACT:
        return V0
    return max(V0 - BRAKE * (min(t, T_IMPACT) - T_V1_REACT), 0.0)


def speed_v2(t):
    if t < T_V2_REACT:
        return V0
    return max(V0 - BRAKE * (min(t, T_IMPACT) - T_V2_REACT), 0.0)


def lateral_rate_v1(t):
    """dy/dt for V1 (positive = toward the eastbound lane / south)"""
    if T_DRIFT_START <= t < T_DRIFT_END:   # derivative of the cosine drift
        span = T_DRIFT_END - T_DRIFT_START
        dy = 1.3 - Y_WB_INNER
        return dy * 0.5 * math.pi / span * math.sin(math.pi * (t - T_DRIFT_START) / span)
    if T_V1_REACT <= t <= T_IMPACT:        # steer right: ramp to impact heading
        f = (t - T_V1_REACT) / (T_IMPACT - T_V1_REACT)
        return f * speed_v1(T_IMPACT) * math.sin(V1_IMPACT_YAW)
    return 0.0


def lateral_rate_v2(t):
    if T_V2_REACT <= t <= T_IMPACT:        # steer left (north, -y)
        f = (t - T_V2_REACT) / (T_IMPACT - T_V2_REACT)
        return -f * speed_v2(T_IMPACT) * math.sin(V2_IMPACT_YAW - math.pi)
    return 0.0


def integrate(speed, lat_rate, direction, y0):
    """direction +1 drives +x, -1 drives -x. Returns [(t, x, y, yaw)] up to impact,
    with x relative to an arbitrary start (shifted later)."""
    pts, x, y, t = [], 0.0, y0, 0.0
    while t <= T_IMPACT + 1e-9:
        v = speed(t)
        vy = lat_rate(t)
        vx = math.sqrt(max(v * v - vy * vy, 0.0)) * direction
        yaw = math.atan2(vy, vx)
        pts.append((t, x, y, yaw))
        x += vx * DT
        y += vy * DT
        t = round(t + DT, 6)
    return pts


def post_impact(p_imp, rest_dx, rest_dy, rest_yaw):
    """impact pose -> rest pose over T_IMPACT..T_REST, decelerating (ease-out)"""
    t0, x0, y0, h0 = p_imp
    while rest_yaw - h0 > math.pi:      # take the short way round
        rest_yaw -= 2 * math.pi
    while rest_yaw - h0 < -math.pi:
        rest_yaw += 2 * math.pi
    out = []
    t = T_IMPACT + DT
    while t <= T_REST + 1e-9:
        f = (t - T_IMPACT) / (T_REST - T_IMPACT)
        e = 1 - (1 - f) ** 3          # fast at first, then settles
        out.append((round(t, 6), x0 + rest_dx * e, y0 + rest_dy * e, h0 + (rest_yaw - h0) * e))
        t = round(t + DT, 6)
    out.append((T_END, x0 + rest_dx, y0 + rest_dy, rest_yaw))
    return out


def build_trajectories():
    v1 = integrate(speed_v1, lateral_rate_v1, +1, Y_WB_INNER)
    v2 = integrate(speed_v2, lateral_rate_v2, -1, Y_EB)
    # place them so the front bumpers meet at IMPACT_X (0.15 m overlap so
    # esmini's bounding-box collision check fires)
    t, x1, y1, h1 = v1[-1]
    front1 = x1 + V1["L"] / 2 * math.cos(h1)
    s1 = IMPACT_X + 0.075 - front1
    t, x2, y2, h2 = v2[-1]
    front2 = x2 + V2["L"] / 2 * math.cos(h2)
    s2 = IMPACT_X - 0.075 - front2
    v1 = [(t, x + s1, y, h) for (t, x, y, h) in v1]
    v2 = [(t, x + s2, y, h) for (t, x, y, h) in v2]
    # post impact: near-equal momenta cancel; small net drift west and north,
    # slight separation as they spin apart
    v1 += post_impact(v1[-1], -0.6, -0.4, V1_REST_YAW)
    v2 += post_impact(v2[-1], +1.4, -0.7, V2_REST_YAW)
    return v1, v2


# ---------------------------------------------------------------- OpenDRIVE
def xodr():
    def lane(lid, ltype, width, mark):
        rm = ""
        if mark:
            mtype, color = mark
            rm = (f'<roadMark sOffset="0" type="{mtype}" weight="standard" color="{color}" '
                  f'width="0.15" laneChange="none"/>')
        w = f'<width sOffset="0" a="{width}" b="0" c="0" d="0"/>' if lid != 0 else ""
        return f'<lane id="{lid}" type="{ltype}" level="false"><link/>{w}{rm}</lane>'

    left = (lane(2, "shoulder", SHOULDER_W, None) +
            lane(1, "driving", LANE_W, ("solid", "standard")))
    center = lane(0, "none", 0, ("solid solid", "yellow"))
    right = (lane(-1, "driving", LANE_W, ("broken", "standard")) +
             lane(-2, "driving", LANE_W, ("solid", "standard")) +
             lane(-3, "shoulder", SHOULDER_W, None))
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<OpenDRIVE>
  <header revMajor="1" revMinor="6" name="CIREN case 11 road" version="1.0" date="2026-11-18"
          north="0" south="0" east="0" west="0"/>
  <!-- Straight road, +x = west. Lanes: +1 eastbound, -1/-2 westbound. -->
  <road name="CaseRoad" length="{ROAD_LEN}" id="1" junction="-1">
    <link/>
    <type s="0" type="rural"><speed max="80" unit="km/h"/></type>
    <planView>
      <geometry s="0" x="0" y="0" hdg="0" length="{ROAD_LEN}"><line/></geometry>
    </planView>
    <elevationProfile>
      <elevation s="0" a="0" b="{GRADE}" c="0" d="0"/>
    </elevationProfile>
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


# ---------------------------------------------------------------- OpenSCENARIO
def f3(v):
    return f"{v:.3f}"


def vehicle_xml(v):
    return (f'<ScenarioObject name="{v["name"]}"><Vehicle name="{v["name"]}" vehicleCategory="car" '
            f'model3d="../models/{v["model"]}.osgb"><ParameterDeclarations/>'
            f'<BoundingBox><Center x="0" y="0" z="{f3(v["H"] / 2)}"/>'
            f'<Dimensions width="{v["W"]}" length="{v["L"]}" height="{v["H"]}"/></BoundingBox>'
            f'<Performance maxSpeed="70" maxAcceleration="10" maxDeceleration="12"/>'
            f'<Axles><FrontAxle maxSteering="0.6" wheelDiameter="0.62" trackWidth="1.5" positionX="2.65" positionZ="0.31"/>'
            f'<RearAxle maxSteering="0" wheelDiameter="0.62" trackWidth="1.5" positionX="0" positionZ="0.31"/></Axles>'
            f'<Properties><Property name="scaleMode" value="ModelToBB"/></Properties>'
            f'</Vehicle></ScenarioObject>')


def time_trigger(name, t):
    return (f'<StartTrigger><ConditionGroup><Condition name="{name}" delay="0" conditionEdge="none">'
            f'<ByValueCondition><SimulationTimeCondition value="{f3(t)}" rule="greaterOrEqual"/>'
            f'</ByValueCondition></Condition></ConditionGroup></StartTrigger>')


def trajectory_mg(v, pts):
    verts = "\n".join(
        f'            <Vertex time="{f3(t)}"><Position><WorldPosition x="{f3(x)}" y="{f3(y)}" h="{h:.4f}"/></Position></Vertex>'
        for (t, x, y, h) in pts)
    n = v["name"]
    return f'''      <ManeuverGroup name="{n}_mg" maximumExecutionCount="1">
        <Actors selectTriggeringEntities="false"><EntityRef entityRef="{n}"/></Actors>
        <Maneuver name="{n}_reconstructed_path">
          <Event name="{n}_drive" priority="overwrite">
            <Action name="{n}_follow_path">
              <PrivateAction><RoutingAction><FollowTrajectoryAction>
                <TrajectoryRef><Trajectory name="{n}_path" closed="false"><Shape><Polyline>
{verts}
                </Polyline></Shape></Trajectory></TrajectoryRef>
                <TimeReference><Timing domainAbsoluteRelative="absolute" scale="1" offset="0"/></TimeReference>
                <TrajectoryFollowingMode followingMode="position"/>
              </FollowTrajectoryAction></RoutingAction></PrivateAction>
            </Action>
            {time_trigger(n + "_start", 0)}
          </Event>
        </Maneuver>
      </ManeuverGroup>'''


def xosc(v1_pts, v2_pts):
    def init(v, p):
        return (f'<Private entityRef="{v["name"]}"><PrivateAction><TeleportAction><Position>'
                f'<WorldPosition x="{f3(p[1])}" y="{f3(p[2])}" h="{p[3]:.4f}"/>'
                f'</Position></TeleportAction></PrivateAction></Private>')

    impact_event = f'''      <ManeuverGroup name="ImpactMonitor_mg" maximumExecutionCount="1">
        <Actors selectTriggeringEntities="false"><EntityRef entityRef="{V1['name']}"/></Actors>
        <Maneuver name="ImpactMonitor">
          <!-- Fires (and is logged) when the two bounding boxes touch -->
          <Event name="Impact" priority="parallel">
            <Action name="RecordImpact">
              <GlobalAction><ParameterAction parameterRef="Impacted"><SetAction value="true"/></ParameterAction></GlobalAction>
            </Action>
            <StartTrigger><ConditionGroup>
              <Condition name="V1_hits_V2" delay="0" conditionEdge="rising"><ByEntityCondition>
                <TriggeringEntities triggeringEntitiesRule="any"><EntityRef entityRef="{V1['name']}"/></TriggeringEntities>
                <EntityCondition><CollisionCondition><EntityRef entityRef="{V2['name']}"/></CollisionCondition></EntityCondition>
              </ByEntityCondition></Condition>
            </ConditionGroup></StartTrigger>
          </Event>
        </Maneuver>
      </ManeuverGroup>'''

    return f'''<?xml version="1.0" encoding="UTF-8"?>
<!--
  CIREN case 11 (NHTSA 3-C4-2017-002) reconstruction for esmini.
  Head-on: 2014 Ford Focus (V1, red, westbound) drifted across the double
  yellow line into a 2010 Honda Civic (V2, blue, eastbound). Dark, unlit,
  dry, straight road, 80 km/h limit.

  Timeline (s):  0 both at 80 km/h | {T_DRIFT_START} V1 starts drifting left
                 {T_V2_REACT} V2 brakes + steers left | {T_V1_REACT} V1 brakes + steers right
                 {T_IMPACT} impact (~55 km/h each) | {T_REST} at rest | {T_END} end
  Speeds, timing and post-impact motion are assumptions; see ciren_case11.py.
  Real world: +x = west, +y = south.
-->
<OpenSCENARIO>
  <FileHeader revMajor="1" revMinor="1" date="2026-11-18T00:00:00"
              description="CIREN case 11 head-on reconstruction" author="Marco Walther"/>
  <ParameterDeclarations>
    <ParameterDeclaration name="Impacted" parameterType="boolean" value="false"/>
  </ParameterDeclarations>
  <CatalogLocations/>
  <RoadNetwork>
    <LogicFile filepath="{OUT_XODR}"/>
  </RoadNetwork>
  <Entities>
    {vehicle_xml(V1)}
    {vehicle_xml(V2)}
  </Entities>
  <Storyboard>
    <Init><Actions>
      {init(V1, v1_pts[0])}
      {init(V2, v2_pts[0])}
    </Actions></Init>
    <Story name="Case11">
      <Act name="Crash">
{trajectory_mg(V1, v1_pts)}
{trajectory_mg(V2, v2_pts)}
{impact_event}
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
    v1, v2 = build_trajectories()
    with open(OUT_XODR, "w", encoding="utf-8") as f:
        f.write(xodr())
    with open(OUT_XOSC, "w", encoding="utf-8") as f:
        f.write(xosc(v1, v2))
    imp1 = [p for p in v1 if abs(p[0] - T_IMPACT) < 1e-6][0]
    imp2 = [p for p in v2 if abs(p[0] - T_IMPACT) < 1e-6][0]
    print(f"V1 start x={v1[0][1]:.1f} y={v1[0][2]:.2f}; impact x={imp1[1]:.2f} y={imp1[2]:.2f} "
          f"yaw={math.degrees(imp1[3]):.1f} speed={speed_v1(T_IMPACT) * 3.6:.0f} km/h")
    print(f"V2 start x={v2[0][1]:.1f} y={v2[0][2]:.2f}; impact x={imp2[1]:.2f} y={imp2[2]:.2f} "
          f"yaw={math.degrees(imp2[3]):.1f} speed={speed_v2(T_IMPACT) * 3.6:.0f} km/h")
    print(f"max V1 encroachment y={max(p[2] for p in v1 if p[0] <= T_IMPACT):.2f} m (centre line y=0)")
