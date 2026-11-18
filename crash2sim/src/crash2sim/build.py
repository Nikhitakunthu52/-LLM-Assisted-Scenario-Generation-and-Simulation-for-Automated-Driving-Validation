"""Scenario spec (JSON) -> OpenSCENARIO (.xosc) via templates."""
from __future__ import annotations

import datetime as dt
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TEMPLATES = ROOT / "templates"
ASSETS = ROOT / "sim_assets"

EGO_MODEL = {"car": "car_white", "suv": "car_white", "pickup": "car_white", "truck": "truck_yellow",
             "van": "van_red", "bus": "bus_blue", "motorcycle": "motorbike"}
OTHER_MODEL = {"car": "car_red", "suv": "car_blue", "pickup": "car_blue", "truck": "truck_yellow",
               "van": "van_red", "bus": "bus_blue", "motorcycle": "motorbike"}

LIGHT_TIME = {"day": "12:00:00", "dusk": "19:30:00", "night": "23:00:00"}
SURFACE_FRICTION = {"dry": 1.0, "wet": 0.7, "icy": 0.3}


def kph(v: float) -> float:
    return round(float(v) / 3.6, 3)


def _render(template: str, values: dict) -> str:
    def sub(m):
        key = m.group(1)
        if key not in values:
            raise KeyError(f"template placeholder '{key}' has no value")
        return str(values[key])
    return re.sub(r"\{\{(\w+)\}\}", sub, template)


def environment_action(env: dict) -> str:
    precip, intensity, fog = "dry", 0.0, 100000
    if env["weather"] == "rain":
        precip, intensity = "rain", 5.0
    elif env["weather"] == "snow":
        precip, intensity = "snow", 5.0
    elif env["weather"] == "fog":
        fog = 60
    if env["light"] == "night":
        sun_elev, illum = -0.3, 0.1
    elif env["light"] == "dusk":
        sun_elev, illum = 0.05, 400
    else:
        sun_elev, illum = 0.8, 90000
    return f"""            <GlobalAction>
               <EnvironmentAction>
                  <Environment name="ReportEnvironment">
                     <TimeOfDay animation="false" dateTime="2026-11-20T{LIGHT_TIME[env['light']]}"/>
                     <Weather fractionalCloudCover="{'eightOktas' if precip != 'dry' or fog < 1000 else 'oneOktas'}">
                        <Sun azimuth="0.0" illuminance="{illum}" elevation="{sun_elev}"/>
                        <Fog visualRange="{fog}"/>
                        <Precipitation precipitationType="{precip}" precipitationIntensity="{intensity}"/>
                     </Weather>
                     <RoadCondition frictionScaleFactor="{SURFACE_FRICTION[env['surface']]}"/>
                  </Environment>
               </EnvironmentAction>
            </GlobalAction>"""


def _brake_group(trigger_xml: str) -> str:
    return f"""            <ManeuverGroup maximumExecutionCount="1" name="EgoReactionGroup">
               <Actors selectTriggeringEntities="false"><EntityRef entityRef="Ego"/></Actors>
               <Maneuver name="EgoReaction">
                  <Event name="EgoBrakeEvent" priority="override" maximumExecutionCount="1">
                     <Action name="EgoBrakeAction">
                        <PrivateAction>
                           <LongitudinalAction>
                              <SpeedAction>
                                 <SpeedActionDynamics dynamicsShape="linear" dynamicsDimension="rate" value="$EgoBrakeDecel"/>
                                 <SpeedActionTarget><AbsoluteTargetSpeed value="0"/></SpeedActionTarget>
                              </SpeedAction>
                           </LongitudinalAction>
                        </PrivateAction>
                     </Action>
                     <StartTrigger>
                        <ConditionGroup>
{trigger_xml}
                        </ConditionGroup>
                     </StartTrigger>
                  </Event>
               </Maneuver>
            </ManeuverGroup>"""


def _collision_group(other: str) -> str:
    """When the two vehicles touch, bring both to rest (esmini has no crash physics)."""
    return f"""            <ManeuverGroup maximumExecutionCount="1" name="ImpactGroup">
               <Actors selectTriggeringEntities="false"><EntityRef entityRef="Ego"/><EntityRef entityRef="{other}"/></Actors>
               <Maneuver name="Impact">
                  <Event name="ImpactEvent" priority="override" maximumExecutionCount="1">
                     <Action name="ImpactStop">
                        <PrivateAction>
                           <LongitudinalAction>
                              <SpeedAction>
                                 <SpeedActionDynamics dynamicsShape="linear" dynamicsDimension="rate" value="25"/>
                                 <SpeedActionTarget><AbsoluteTargetSpeed value="0"/></SpeedActionTarget>
                              </SpeedAction>
                           </LongitudinalAction>
                        </PrivateAction>
                     </Action>
                     <StartTrigger>
                        <ConditionGroup>
                           <Condition name="ImpactDetected" delay="0" conditionEdge="rising">
                              <ByEntityCondition>
                                 <TriggeringEntities triggeringEntitiesRule="any"><EntityRef entityRef="Ego"/></TriggeringEntities>
                                 <EntityCondition><CollisionCondition><EntityRef entityRef="{other}"/></CollisionCondition></EntityCondition>
                              </ByEntityCondition>
                           </Condition>
                        </ConditionGroup>
                     </StartTrigger>
                  </Event>
               </Maneuver>
            </ManeuverGroup>"""


def _stop_conditions(max_time: float) -> str:
    return f"""         <ConditionGroup>
            <Condition name="StopAfterImpact" delay="2" conditionEdge="rising">
               <ByValueCondition>
                  <StoryboardElementStateCondition storyboardElementType="event" storyboardElementRef="ImpactEvent" state="endTransition"/>
               </ByValueCondition>
            </Condition>
         </ConditionGroup>
         <ConditionGroup>
            <Condition name="EgoStopped" delay="1.5" conditionEdge="rising">
               <ByEntityCondition>
                  <TriggeringEntities triggeringEntitiesRule="any"><EntityRef entityRef="Ego"/></TriggeringEntities>
                  <EntityCondition><SpeedCondition value="0.05" rule="lessThan"/></EntityCondition>
               </ByEntityCondition>
            </Condition>
         </ConditionGroup>
         <ConditionGroup>
            <Condition name="Timeout" delay="0" conditionEdge="rising">
               <ByValueCondition><SimulationTimeCondition value="{max_time}" rule="greaterThan"/></ByValueCondition>
            </Condition>
         </ConditionGroup>"""


def _cond_after_event(event: str, delay: float) -> str:
    return f"""                           <Condition name="HazardPerceived" delay="{delay}" conditionEdge="none">
                              <ByValueCondition>
                                 <StoryboardElementStateCondition storyboardElementType="event" storyboardElementRef="{event}" state="startTransition"/>
                              </ByValueCondition>
                           </Condition>"""


def _cond_ttc(other: str, ttc: float, delay: float) -> str:
    return f"""                           <Condition name="HazardPerceived" delay="{delay}" conditionEdge="rising">
                              <ByEntityCondition>
                                 <TriggeringEntities triggeringEntitiesRule="any"><EntityRef entityRef="Ego"/></TriggeringEntities>
                                 <EntityCondition>
                                    <TimeToCollisionCondition value="{ttc}" freespace="true" rule="lessThan" relativeDistanceType="longitudinal" coordinateSystem="road">
                                       <TimeToCollisionConditionTarget><EntityRef entityRef="{other}"/></TimeToCollisionConditionTarget>
                                    </TimeToCollisionCondition>
                                 </EntityCondition>
                              </ByEntityCondition>
                           </Condition>"""


def _cond_distance(other: str, dist_param: str, delay: float) -> str:
    return f"""                           <Condition name="HazardPerceived" delay="{delay}" conditionEdge="rising">
                              <ByEntityCondition>
                                 <TriggeringEntities triggeringEntitiesRule="any"><EntityRef entityRef="Ego"/></TriggeringEntities>
                                 <EntityCondition>
                                    <RelativeDistanceCondition entityRef="{other}" freespace="true" relativeDistanceType="euclidianDistance" rule="lessThan" value="{dist_param}"/>
                                 </EntityCondition>
                              </ByEntityCondition>
                           </Condition>"""


def build_xosc(spec: dict, report_id: str, out_dir: Path) -> Path:
    """Render a validated + sanitized spec into an .xosc file. Returns the path."""
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{report_id}.xosc"
    assets = os.path.relpath(ASSETS, out_dir).replace(os.sep, "/")
    ego, oth, env = spec["ego"], spec["other"], spec["environment"]
    rt = round(float(ego["reaction_time_s"]), 2)

    common = {
        "report_id": report_id,
        "date": dt.datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "assets": assets,
        "ego_model": EGO_MODEL[ego["vehicle"]],
        "other_model": OTHER_MODEL[oth["vehicle"]],
        "ego_speed": kph(ego["speed_kph"]),
        "reaction_time": rt,
        "ego_decel": round(float(ego["brake_decel_mps2"]) or 6.0, 2),
        "environment_action": environment_action(env),
    }

    if spec["scenario_type"] == "rear_end":
        other = "Lead"
        if oth["maneuver"] == "decelerate":
            trigger = _cond_after_event("LeadBrakeEvent", rt)
        else:  # stopped / constant_speed: driver perceives closing at TTC 4 s
            trigger = _cond_ttc(other, 4.0, rt)
        values = dict(common,
                      lead_speed=kph(oth["speed_kph"]),
                      lead_final_speed=kph(oth["final_speed_kph"]),
                      lead_decel=round(float(oth["decel_mps2"]) or 0.01, 2),
                      lead_brake_time=2.0 if oth["maneuver"] == "decelerate" else 9999,
                      ego_start_s=30,
                      lead_start_s=round(30 + float(oth["gap_m"]), 1),
                      ego_reaction_group=_brake_group(trigger) if ego["reacts"] else "",
                      collision_group=_collision_group(other),
                      stop_conditions=_stop_conditions(25))
        tmpl = "rear_end.xosc.tmpl"
    else:
        other = "NPC"
        # Place the turning vehicle so it reaches the conflict point at its own (reported) speed:
        # Ego needs ~55 m along its route to reach the sync point.
        t_ego = 55.0 / max(kph(ego["speed_kph"]), 1.0)
        npc_avg = (kph(oth["speed_kph"]) + kph(oth["final_speed_kph"])) / 2
        npc_start = round(min(195.0, max(0.0, 203.0 - npc_avg * t_ego)), 1)
        hazard = 25 if env["light"] in ("night", "dusk") or env["weather"] in ("fog", "rain", "snow") else 35
        values = dict(common,
                      npc_speed=kph(oth["speed_kph"]),
                      npc_final_speed=kph(oth["final_speed_kph"]),
                      ego_start_s=0,
                      ego_sync_s=7,
                      npc_sync_s=203,
                      npc_start_s=npc_start,
                      hazard_distance=hazard,
                      ego_reaction_group=_brake_group(_cond_distance(other, "$HazardDistance", rt)) if ego["reacts"] else "",
                      collision_group=_collision_group(other),
                      stop_conditions=_stop_conditions(30))
        tmpl = "ltap_od.xosc.tmpl"

    xml = _render((TEMPLATES / tmpl).read_text(), values)
    out.write_text(xml)
    return out
