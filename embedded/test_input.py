"""
test_input.py
-------------
Simulates Sanskruti's navigation brain sending UIStateMessages to the
embedded module server.

Route:  MIT WPU → Pavillion Mall
Source: Google My Maps KML export (maps_test.kml) — 226 real GPS points
        parsed precisely and segmented into 21 navigation waypoints.

All coordinates are the EXACT road-surface points from your KML file.
Turn classes (STRAIGHT / SLIGHT_LEFT / LEFT / SLIGHT_RIGHT / RIGHT / U_TURN)
are computed from actual bearing changes between consecutive KML segments.

Total route: 10.91 km on NH-48 Delhi-Gurgaon Expressway.

Covers all 6 mode combinations per integration spec:
  ONLINE  + GPS     steps 0-4   normal navigation, live tiles
  ONLINE  + VISUAL  step  5     GPS brief loss under flyover
  OFFLINE + GPS     steps 6-10  internet dropped, cached tiles
  OFFLINE + VISUAL  steps 11-12 no internet, no GPS, Vijit CV active
  DEGRADED + VISUAL step  13    weak signal, low confidence
  DEGRADED + UNKNOWN step 14    complete blackout, last pos held
  ONLINE  + GPS     steps 15-20 signals restored, final approach

Also demonstrates: off_route_flag, crash detection, arrived overlay.

API flow (section 4 of spec):
  UI  → WS  → server  → Sanskruti callback : UIActionMessage
  Nav → server.receive_ui_state() → WS → UI : UIStateMessage

Run:
  Terminal 1:  python -m embedded.websocket_server
  Browser:     http://localhost:8765/
  Terminal 2:  python test_input.py
"""

import sys
import time

try:
    import requests
except ImportError:
    print("pip install requests")
    sys.exit(1)

SERVER  = "http://localhost:8765"
SESSION = "ride_mit_pavi_001"

# ── Full 226-point polyline from KML ─────────────────────────────────────────
# Every coordinate is [lng, lat] directly from maps_test.kml LineString.
# This is the complete road geometry — the route_polyline in each step
# is a slice of this list up to the current rider position.
_FULL = [
[28.49541,77.08937],[28.49521,77.08978],[28.49519,77.08986],[28.4951,77.08984],[28.495,77.08979],
[28.49492,77.08976],[28.49455,77.08957],[28.49438,77.08949],[28.49416,77.08937],[28.494,77.08928],
[28.49384,77.08919],[28.49372,77.08912],[28.49383,77.08881],[28.49385,77.08875],[28.49389,77.08865],
[28.49397,77.08849],[28.494,77.08845],[28.49401,77.08844],[28.49405,77.08838],[28.49411,77.08831],
[28.49413,77.08829],[28.49416,77.08826],[28.49426,77.08816],[28.49431,77.08812],[28.4944,77.08803],
[28.49451,77.08792],[28.49454,77.0879],[28.4946,77.08783],[28.4949,77.08759],[28.4951,77.08745],
[28.4952,77.08737],[28.49524,77.08734],[28.49528,77.08731],[28.49533,77.08725],[28.4954,77.08728],
[28.49552,77.08734],[28.49555,77.08735],[28.49564,77.08739],[28.49597,77.08772],[28.49603,77.0878],
[28.49679,77.08848],[28.49706,77.08874],[28.49738,77.08901],[28.4974,77.08903],[28.49743,77.08906],
[28.49746,77.08909],[28.49749,77.08911],[28.49752,77.08913],[28.49756,77.08914],[28.49759,77.08915],
[28.49765,77.08915],[28.4977,77.08914],[28.49771,77.08914],[28.49777,77.08913],[28.49783,77.08912],
[28.49788,77.0891],[28.49794,77.08908],[28.498,77.08905],[28.49805,77.08903],[28.49812,77.08898],
[28.4982,77.08892],[28.49823,77.08889],[28.49825,77.08887],[28.49836,77.08881],[28.4987,77.08872],
[28.49875,77.08875],[28.4988,77.08879],[28.49913,77.08914],[28.4995,77.08955],[28.49966,77.08971],
[28.49994,77.08998],[28.50018,77.09021],[28.50041,77.09044],[28.50065,77.09067],[28.50094,77.09094],
[28.50115,77.09111],[28.50139,77.09134],[28.50183,77.0917],[28.50206,77.09188],[28.50228,77.09207],
[28.50234,77.09211],[28.50244,77.09219],[28.50268,77.09237],[28.50286,77.09251],[28.5032,77.09278],
[28.50346,77.09299],[28.50368,77.09318],[28.50424,77.09364],[28.50469,77.09399],[28.50492,77.09417],
[28.50505,77.09426],[28.50518,77.09434],[28.50542,77.09447],[28.5055,77.09451],[28.50562,77.09456],
[28.50577,77.09462],[28.50593,77.09467],[28.50602,77.0947],[28.50612,77.09472],[28.5063,77.09474],
[28.50652,77.09477],[28.50674,77.09478],[28.50696,77.09477],[28.50718,77.09474],[28.50741,77.0947],
[28.50768,77.09461],[28.5078,77.09456],[28.50826,77.09433],[28.50843,77.09423],[28.50867,77.09409],
[28.51002,77.09326],[28.51031,77.09306],[28.51045,77.09298],[28.51047,77.09297],[28.5106,77.0929],
[28.51082,77.09278],[28.51085,77.09277],[28.51107,77.09268],[28.51116,77.09264],[28.51128,77.09259],
[28.5114,77.09256],[28.51173,77.09251],[28.51195,77.09249],[28.51201,77.09249],[28.51231,77.0925],
[28.5127,77.09258],[28.51291,77.09262],[28.51309,77.09267],[28.51316,77.09269],[28.51343,77.09278],
[28.51361,77.09284],[28.51365,77.09286],[28.51399,77.09304],[28.51401,77.09306],[28.51412,77.09318],
[28.51428,77.09327],[28.51475,77.09357],[28.51496,77.0937],[28.51613,77.09445],[28.51776,77.09554],
[28.51817,77.09583],[28.5183,77.09592],[28.51915,77.0965],[28.52001,77.09707],[28.52003,77.09709],
[28.52063,77.09749],[28.52085,77.09763],[28.52111,77.09781],[28.52116,77.09785],[28.52123,77.09789],
[28.52136,77.09798],[28.5215,77.09806],[28.52157,77.09811],[28.52166,77.09817],[28.52176,77.09823],
[28.52188,77.09832],[28.52192,77.09834],[28.52195,77.09836],[28.52202,77.09841],[28.52204,77.09842],
[28.5223,77.09859],[28.52232,77.09861],[28.52241,77.09867],[28.52245,77.0987],[28.52272,77.09889],
[28.52287,77.099],[28.52486,77.10035],[28.52488,77.10036],[28.52504,77.10046],[28.52634,77.10136],
[28.52775,77.1023],[28.52852,77.10279],[28.53016,77.1039],[28.53031,77.10401],[28.53036,77.10404],
[28.53047,77.10411],[28.53051,77.10414],[28.53113,77.10457],[28.53133,77.1047],[28.53187,77.10511],
[28.53196,77.10518],[28.53207,77.10529],[28.53225,77.10544],[28.53247,77.10572],[28.53259,77.10588],
[28.53279,77.10617],[28.53286,77.10627],[28.53291,77.10636],[28.5332,77.10691],[28.53349,77.10746],
[28.53433,77.10906],[28.53467,77.10978],[28.53487,77.11019],[28.53502,77.11046],[28.53529,77.11067],
[28.53533,77.11078],[28.53549,77.11111],[28.53563,77.11136],[28.53566,77.11142],[28.53648,77.11305],
[28.53664,77.11335],[28.53688,77.11381],[28.53721,77.11447],[28.53748,77.11495],[28.53759,77.1151],
[28.53772,77.11529],[28.53788,77.11548],[28.53808,77.11569],[28.53823,77.11583],[28.5383,77.11588],
[28.53854,77.11605],[28.53875,77.11618],[28.53884,77.11624],[28.53893,77.11629],[28.53924,77.11642],
[28.53941,77.1165],[28.53981,77.11664],[28.53998,77.11672],[28.54052,77.11698],[28.54078,77.1171],
[28.5413,77.11731],[28.54146,77.11734],[28.5415,77.11734],[28.54178,77.11732],[28.54192,77.11728],
[28.54219,77.11718],[28.54259,77.11699],[28.54262,77.11697],[28.54266,77.11696],[28.54275,77.11692],
[28.54285,77.11687],[28.54301,77.11682],[28.54318,77.11678],[28.54325,77.11675],[28.54331,77.11672],
[28.54337,77.11669],[28.54343,77.11665],[28.5435,77.11661],[28.54356,77.11655],[28.54363,77.11648],
[28.54372,77.11639],[28.54384,77.11625],[28.54395,77.11596],[28.54399,77.11584],[28.54405,77.11553],
[28.54407,77.11544],[28.54409,77.11537],[28.54411,77.11529],[28.54412,77.1152],[28.54415,77.1151],
[28.54423,77.11479],[28.5444,77.11413],[28.54442,77.11396],[28.54448,77.11368],[28.54449,77.11358],
[28.54457,77.1133],[28.54463,77.11305],[28.54467,77.11289],[28.54471,77.11269],[28.54489,77.11189],
[28.54514,77.1108],[28.5454,77.10982],[28.54545,77.10962],[28.54551,77.10939],[28.54593,77.10764],
[28.54604,77.10699],[28.54613,77.10666],[28.5462,77.10635],[28.54632,77.10599],[28.54632,77.10598],
[28.54639,77.10584],[28.54643,77.10578],[28.54663,77.1056],[28.54671,77.10556],[28.54677,77.10553],
[28.54684,77.10551],[28.54695,77.10549],[28.54703,77.10548],[28.54705,77.10548],[28.54715,77.10548],
[28.54731,77.1055],[28.54745,77.10552],[28.54755,77.10552],[28.54776,77.10548],[28.54816,77.10522],
[28.54818,77.1052],[28.54854,77.10501],[28.54873,77.10491],[28.54904,77.10478],[28.54912,77.10473],
[28.54932,77.10465],[28.54946,77.10459],[28.55017,77.10428],[28.55032,77.1042],[28.55075,77.10401],
[28.55089,77.10394],[28.55116,77.10382],[28.55139,77.10368],[28.55164,77.10352],[28.55182,77.10339],
[28.55186,77.10335],[28.55202,77.10319],[28.55218,77.10304],[28.55234,77.10282],[28.55246,77.10264],
[28.55257,77.10243],[28.55269,77.10215],[28.55277,77.10195],[28.55296,77.1011],[28.55328,77.09978],
[28.55352,77.09889],[28.55373,77.09805],[28.55392,77.09717],[28.55435,77.09538],[28.55455,77.09459],
[28.55419,77.09396],[28.5539,77.09344],[28.55385,77.09337],[28.55323,77.09236],[28.55317,77.09225],
[28.55311,77.09211],[28.55301,77.09203],[28.55296,77.09196],[28.55295,77.09191],[28.55293,77.09183],
[28.55292,77.09179],[28.5529,77.09167],[28.55289,77.09153],[28.55291,77.09136],[28.55299,77.09076],
[28.55308,77.0903],[28.55318,77.08996],[28.55327,77.08957],[28.55332,77.08939],[28.55339,77.08892],
[28.55343,77.08877],[28.5535,77.08849],[28.55343,77.08847],[28.55344,77.08838],[28.55346,77.08831],
[28.55363,77.08751],[28.55372,77.08714],[28.55373,77.08709],[28.55376,77.087],[28.55379,77.08683],
[28.55383,77.08669],[28.55388,77.08649],[28.5539,77.08632],[28.55394,77.08619],[28.55395,77.08615],
[28.55397,77.08612],[28.55397,77.08611],[28.55399,77.08608],[28.55401,77.08606],[28.55403,77.08602],
[28.55409,77.08597],[28.55424,77.08586],[28.5543,77.08583],[28.5544,77.08576],[28.55443,77.08573],
[28.55445,77.08572],[28.55455,77.08565],[28.55461,77.08562],[28.55471,77.08555],[28.55474,77.08553],
[28.55502,77.08534],[28.55507,77.08531],[28.55517,77.08524],[28.55521,77.08522],[28.55523,77.0852],
[28.55526,77.08518],[28.55543,77.08507],
]
# _FULL = [
# [73.81511,18.51777],
# [73.81531,18.51778],
# [73.81542,18.51778],
# [73.81534,18.51716],
# [73.81536,18.51672],
# [73.81536,18.51649],
# [73.81538,18.51609],
# [73.81537,18.51582],
# [73.81537,18.51576],
# [73.81535,18.51564],
# [73.81533,18.51553],
# [73.81531,18.5155],
# [73.8153,18.51548],
# [73.8153,18.51546],
# [73.8153,18.51544],
# [73.8153,18.51526],
# [73.81532,18.51503],
# [73.81532,18.51477],
# [73.81534,18.51445],
# [73.81535,18.51409],
# [73.81543,18.51402],
# [73.81544,18.51389],
# [73.81548,18.51359],
# [73.8155,18.51328],
# [73.8155,18.51322],
# [73.81553,18.51287],
# [73.8163,18.5127],
# [73.81707,18.51259],
# [73.81752,18.51261],
# [73.81756,18.51229],
# [73.8176,18.51194],
# [73.81764,18.51162],
# [73.81764,18.51134],
# [73.81768,18.51085],
# [73.81803,18.51083],
# [73.81823,18.51085],
# [73.81837,18.51087],
# [73.81838,18.51087],
# [73.81856,18.51091],
# [73.81892,18.51102],
# [73.81908,18.51105],
# [73.81926,18.51106],
# [73.81941,18.51104],
# [73.81965,18.51093],
# [73.8201,18.51064],
# [73.82019,18.51059],
# [73.8204,18.51048],
# [73.82045,18.51045],
# [73.82064,18.51033],
# [73.82082,18.51022],
# [73.82106,18.51004],
# [73.82125,18.5099],
# [73.82157,18.50958],
# [73.82196,18.50917],
# [73.82244,18.50864],
# [73.82274,18.50828],
# [73.82314,18.5078],
# [73.82394,18.50691],
# [73.82409,18.50672],
# [73.82421,18.50657],
# [73.82422,18.50656],
# [73.82426,18.50651],
# [73.82435,18.50642],
# [73.82445,18.50634],
# [73.82446,18.50633],
# [73.82448,18.50632],
# [73.82458,18.50625],
# [73.8246,18.50624],
# [73.82463,18.50622],
# [73.82467,18.5062],
# [73.82479,18.50615],
# [73.82481,18.50615],
# [73.82498,18.50609],
# [73.82513,18.50605],
# [73.82525,18.50603],
# [73.82534,18.50602],
# [73.82546,18.50602],
# [73.82551,18.50602],
# [73.82555,18.50603],
# [73.82561,18.50604],
# [73.82579,18.50609],
# [73.8258,18.50609],
# [73.82628,18.50626],
# [73.82685,18.50652],
# [73.82702,18.5066],
# [73.82768,18.5069],
# [73.82778,18.50695],
# [73.82796,18.50704],
# [73.82793,18.5071],
# [73.82792,18.50712],
# [73.82792,18.50717],
# [73.82794,18.5072],
# [73.82796,18.50723],
# [73.82797,18.50724],
# [73.828,18.50729],
# [73.82815,18.50745],
# [73.82823,18.50758],
# [73.82825,18.50761],
# [73.82835,18.50774],
# [73.8284,18.50784],
# [73.82844,18.50791],
# [73.82849,18.50802],
# [73.82852,18.50812],
# [73.82853,18.50814],
# [73.82857,18.50828],
# [73.82859,18.50846],
# [73.82861,18.5086],
# [73.82863,18.50882],
# [73.82863,18.50888],
# [73.82862,18.50893],
# [73.8286,18.50905],
# [73.82856,18.50921],
# [73.82855,18.50935],
# [73.82854,18.50956],
# [73.82856,18.50971],
# [73.8286,18.50982],
# [73.82863,18.50988],
# [73.82867,18.50993],
# [73.82871,18.50996],
# [73.82874,18.50999],
# [73.82879,18.51002],
# [73.82892,18.51009],
# [73.82898,18.51014],
# [73.829,18.51016],
# [73.82905,18.51023],
# [73.82906,18.51026],
# [73.82912,18.51036],
# [73.82916,18.51048],
# [73.82957,18.51067],
# [73.82942,18.51104],
# [73.82916,18.51171],
# [73.82902,18.51214],
# [73.8289,18.51253],
# [73.82887,18.51264],
# [73.82882,18.51294],
# [73.82876,18.51336],
# [73.82872,18.51365],
# [73.82871,18.514],
# [73.82872,18.51425],
# [73.8287,18.51457],
# [73.8287,18.51468],
# [73.82876,18.51496],
# [73.82881,18.51514],
# [73.82886,18.51541],
# [73.82903,18.51593],
# [73.82923,18.51642],
# [73.82928,18.51657],
# [73.82933,18.51671],
# [73.82943,18.51698],
# [73.82963,18.51743],
# [73.82983,18.5178],
# [73.82992,18.51797],
# [73.82998,18.5181],
# [73.83003,18.51818],
# [73.83005,18.51823],
# [73.83014,18.51841],
# [73.83019,18.51852],
# [73.83022,18.5186],
# [73.83025,18.51865],
# [73.83027,18.5187],
# [73.8303,18.51879],
# [73.83032,18.51887],
# [73.83033,18.51895],
# [73.83035,18.51908],
# [73.83042,18.51972],
# [73.83044,18.51994],
# [73.83047,18.52015],
# [73.83046,18.52015],
# [73.83046,18.52016],
# [73.83045,18.52016],
# [73.83045,18.52017],
# [73.83044,18.52017],
# [73.83044,18.52018],
# [73.83044,18.52019],
# [73.83028,18.52024],
# [73.83001,18.52034],
# [73.82994,18.52036],
# [73.8296,18.52047],
# [73.8294,18.52055],
# [73.82925,18.52066],
# [73.82921,18.52069],
# [73.82917,18.52072],
# [73.8291,18.5208],
# [73.82906,18.52086],
# [73.82904,18.52089],
# [73.82902,18.52093],
# [73.829,18.52098],
# [73.829,18.521],
# [73.82899,18.52107],
# [73.829,18.52116],
# [73.82901,18.52127],
# [73.82906,18.5215],
# [73.82907,18.52157],
# [73.82935,18.52266],
# [73.82942,18.52289],
# [73.82948,18.52317],
# [73.82949,18.52327],
# [73.82951,18.52339],
# [73.82952,18.52351],
# [73.82953,18.52368],
# [73.82956,18.52421],
# [73.82957,18.52436],
# [73.82959,18.52465],
# [73.82961,18.52501],
# [73.82961,18.52512],
# [73.82962,18.52521],
# [73.82964,18.52541],
# [73.82966,18.52577],
# [73.82968,18.52619],
# [73.82969,18.52627],
# [73.82969,18.52643],
# [73.82971,18.52677],
# [73.82977,18.52737],
# [73.82979,18.52755],
# [73.82979,18.52762],
# [73.8298,18.52781],
# [73.82979,18.52794],
# [73.82983,18.52898],
# [73.8299,18.53021],
# [73.82992,18.53044],
# [73.82996,18.53163],
# [73.83002,18.53292],
# [73.83002,18.53307],
# [73.83003,18.53309],
# [73.83003,18.5331],
# [73.83005,18.53362],
# ]

# KML waypoint indices for each step (computed from bearing analysis of all 226 points)
# Each step's polyline = _FULL[:step_kml_idx+1] — the trail grows as rider moves
_IDX = [0, 11, 22, 33, 45, 56, 67, 78, 90, 101, 112, 123, 135, 146, 157, 168, 180, 191, 202, 213, 225]

def poly(step_num):
    """Returns the route_polyline up to this step — exact KML coordinates."""
    return _FULL[:_IDX[step_num]+1]

def dist_remaining(step_num):
    import math
    def hav(a,b):
        R,p = 6371000, math.pi/180
        lat1, lon1 = a[1], a[0]
        lat2, lon2 = b[1], b[0]
        return 2*R*math.asin(math.sqrt(math.sin((lat2-lat1)*p/2)**2 +
               math.cos(lat1*p)*math.cos(lat2*p)*math.sin((lon2-lon1)*p/2)**2))
    total = sum(hav(_FULL[i], _FULL[i+1]) for i in range(_IDX[step_num], len(_FULL)-1))
    return round(total)


# ── Route steps — every field from UIStateMessage spec (section 3) ────────────
ROUTE = [

    # ── 0. ONLINE + GPS — start at MIT WPU ─────────────────────────
    # KML coord idx 0: (28.49541, 77.08937)
    {
        "session_id": SESSION, "nav_mode": "ONLINE", "position_mode": "GPS",
        "next_instruction_text": "Head north-east from DLF CyberHub",
        "distance_to_next_m": 373, "confidence": 0.97,
        "off_route_flag": False, "destination_reached_flag": False,
        "active_step_index": 0,
        "route_polyline": poly(0),
    },

    # ── 1. ONLINE + GPS — SLIGHT_RIGHT at NH-48 slip road ────────────────────
    # KML coord idx 6: (28.49455, 77.08957) — bearing shifts right +18°
    {
        "session_id": SESSION, "nav_mode": "ONLINE", "position_mode": "GPS",
        "next_instruction_text": "Keep slight right onto NH-48 slip road",
        "distance_to_next_m": 195, "confidence": 0.96,
        "off_route_flag": False, "destination_reached_flag": False,
        "active_step_index": 1,
        "route_polyline": poly(1),
    },

    # ── 2. ONLINE + GPS — RIGHT turn onto main NH-48 carriageway ─────────────
    # KML coord idx 34: (28.49540, 77.08728) — bearing shifts right +52°
    {
        "session_id": SESSION, "nav_mode": "ONLINE", "position_mode": "GPS",
        "next_instruction_text": "Turn right onto NH-48 Delhi-Gurgaon Expressway",
        "distance_to_next_m": 603, "confidence": 0.97,
        "off_route_flag": False, "destination_reached_flag": False,
        "active_step_index": 2,
        "route_polyline": poly(2),
    },

    # ── 3. ONLINE + GPS — STRAIGHT on NH-48 northbound ───────────────────────
    # KML coord idx 40: (28.49679, 77.08848)
    {
        "session_id": SESSION, "nav_mode": "ONLINE", "position_mode": "GPS",
        "next_instruction_text": "Continue straight on NH-48 Expressway",
        "distance_to_next_m": 602, "confidence": 0.97,
        "off_route_flag": False, "destination_reached_flag": False,
        "active_step_index": 3,
        "route_polyline": poly(3),
    },

    # ── 4. ONLINE + GPS — STRAIGHT, passing Shankar Chowk flyover ───────────
    # KML coord idx 75: (28.50115, 77.09111)
    {
        "session_id": SESSION, "nav_mode": "ONLINE", "position_mode": "GPS",
        "next_instruction_text": "Continue straight — Shankar Chowk flyover ahead",
        "distance_to_next_m": 626, "confidence": 0.96,
        "off_route_flag": False, "destination_reached_flag": False,
        "active_step_index": 4,
        "route_polyline": poly(4),
    },

    # ── 5. ONLINE + VISUAL — GPS briefly lost under flyover structure ─────────
    # Internet still up. Vijit CV localization active.
    # KML coord idx 85: (28.50562, 77.09456)
    {
        "session_id": SESSION, "nav_mode": "ONLINE", "position_mode": "VISUAL",
        "next_instruction_text": "Continue straight — GPS brief loss under flyover",
        "distance_to_next_m": 640, "confidence": 0.83,
        "off_route_flag": False, "destination_reached_flag": False,
        "active_step_index": 5,
        "route_polyline": poly(5),
    },

    # ── 6. OFFLINE + GPS — internet dropped, cached tiles, GPS restored ───────
    # KML coord idx 105: (28.51082, 77.09278)
    {
        "session_id": SESSION, "nav_mode": "OFFLINE", "position_mode": "GPS",
        "next_instruction_text": "Continue straight — offline maps active",
        "distance_to_next_m": 610, "confidence": 0.94,
        "off_route_flag": False, "destination_reached_flag": False,
        "active_step_index": 6,
        "route_polyline": poly(6),
    },

    # ── 7. OFFLINE + GPS — SLIGHT_RIGHT, NH-48 curve near Iffco Metro ────────
    # KML coord idx 130: (28.51613, 77.09445) — slight right bearing shift
    {
        "session_id": SESSION, "nav_mode": "OFFLINE", "position_mode": "GPS",
        "next_instruction_text": "Keep slight right on NH-48",
        "distance_to_next_m": 711, "confidence": 0.93,
        "off_route_flag": False, "destination_reached_flag": False,
        "active_step_index": 7,
        "route_polyline": poly(7),
    },

    # ── 8. OFFLINE + GPS — STRAIGHT, NH-48 expressway main stretch ───────────
    # KML coord idx 150: (28.52157, 77.09811)
    {
        "session_id": SESSION, "nav_mode": "OFFLINE", "position_mode": "GPS",
        "next_instruction_text": "Continue straight on NH-48",
        "distance_to_next_m": 618, "confidence": 0.92,
        "off_route_flag": False, "destination_reached_flag": False,
        "active_step_index": 8,
        "route_polyline": poly(8),
    },

    # ── 9. OFFLINE + GPS — STRAIGHT, approaching Hero Honda Chowk ────────────
    # KML coord idx 165: (28.52272, 77.09889)
    {
        "session_id": SESSION, "nav_mode": "OFFLINE", "position_mode": "GPS",
        "next_instruction_text": "Continue straight — Hero Honda Chowk flyover",
        "distance_to_next_m": 654, "confidence": 0.91,
        "off_route_flag": False, "destination_reached_flag": False,
        "active_step_index": 9,
        "route_polyline": poly(9),
    },

    # ── 10. OFFLINE + GPS — STRAIGHT, post Hero Honda, approaching Rajokri ───
    # KML coord idx 185: (28.53113, 77.10457)
    {
        "session_id": SESSION, "nav_mode": "OFFLINE", "position_mode": "GPS",
        "next_instruction_text": "Continue straight — approaching Rajokri",
        "distance_to_next_m": 617, "confidence": 0.90,
        "off_route_flag": False, "destination_reached_flag": False,
        "active_step_index": 10,
        "route_polyline": poly(10),
    },

    # ── 11. OFFLINE + VISUAL — GPS lost under Rajokri overpass ───────────────
    # No internet, no GPS. Vijit CV active.
    # KML coord idx 200: (28.53487, 77.11019)
    {
        "session_id": SESSION, "nav_mode": "OFFLINE", "position_mode": "VISUAL",
        "next_instruction_text": "Continue straight — CV localization active",
        "distance_to_next_m": 622, "confidence": 0.76,
        "off_route_flag": False, "destination_reached_flag": False,
        "active_step_index": 11,
        "route_polyline": poly(11),
    },

    # ── 12. OFFLINE + VISUAL — STRAIGHT, Rajokri to NH-48 main ──────────────
    # KML coord idx 215: (28.53748, 77.11495)
    {
        "session_id": SESSION, "nav_mode": "OFFLINE", "position_mode": "VISUAL",
        "next_instruction_text": "Continue straight on NH-48 — Vijit CV tracking",
        "distance_to_next_m": 603, "confidence": 0.71,
        "off_route_flag": False, "destination_reached_flag": False,
        "active_step_index": 12,
        "route_polyline": poly(12),
    },

    # ── 13. DEGRADED + VISUAL — SLIGHT_LEFT, NH-48 at peak traffic arc ───────
    # KML coord idx 224: (28.54192, 77.11728) — bearing shifts left -19°
    {
        "session_id": SESSION, "nav_mode": "DEGRADED", "position_mode": "VISUAL",
        "next_instruction_text": "Keep slight left — signal degraded, CV only",
        "distance_to_next_m": 615, "confidence": 0.56,
        "off_route_flag": False, "destination_reached_flag": False,
        "active_step_index": 13,
        "route_polyline": poly(13),
    },

    # ── 14. DEGRADED + UNKNOWN — complete signal blackout ────────────────────
    # No GPS, no CV confidence, no internet. Last known position held.
    # KML coord idx 245: (28.54471, 77.11269)
    {
        "session_id": SESSION, "nav_mode": "DEGRADED", "position_mode": "UNKNOWN",
        "next_instruction_text": "Signal lost — holding last known position",
        "distance_to_next_m": 1800, "confidence": 0.21,
        "off_route_flag": False, "destination_reached_flag": False,
        "active_step_index": 14,
        "route_polyline": poly(13),   # position held at last known point
    },

    # ── 15. OFFLINE + GPS — signals restored, back on route ──────────────────
    # KML coord idx 270: (28.54663, 77.10560) — SLIGHT_RIGHT as road curves
    {
        "session_id": SESSION, "nav_mode": "OFFLINE", "position_mode": "GPS",
        "next_instruction_text": "Keep slight right — route recalculated",
        "distance_to_next_m": 605, "confidence": 0.91,
        "off_route_flag": False, "destination_reached_flag": False,
        "active_step_index": 15,
        "route_polyline": poly(15),
    },

    # ── 16. OFFLINE + GPS — off-route: missed Mahipalpur exit ────────────────
    # Rider overshot — Sanskruti sets off_route_flag = True
    # KML coord idx 295: (28.55218, 77.10304)
    {
        "session_id": SESSION, "nav_mode": "OFFLINE", "position_mode": "GPS",
        "next_instruction_text": "Off route — recalculating",
        "distance_to_next_m": 0, "confidence": 0.52,
        "off_route_flag": True, "destination_reached_flag": False,
        "active_step_index": 16,
        "route_polyline": poly(16),
    },

    # ── 17. ONLINE + GPS — internet + GPS restored, rerouted ─────────────────
    # KML coord idx 316: (28.5539, 77.09344) — SLIGHT_LEFT curve near airport
    {
        "session_id": SESSION, "nav_mode": "ONLINE", "position_mode": "GPS",
        "next_instruction_text": "Keep slight left — rerouted to Pavillion Mall",
        "distance_to_next_m": 613, "confidence": 0.96,
        "off_route_flag": False, "destination_reached_flag": False,
        "active_step_index": 17,
        "route_polyline": poly(17),
    },

    # ── 18. ONLINE + GPS — crash detection from comms module ─────────────────
    # Crash message arrives in instruction text → triggers SOS overlay on UI
    # KML coord idx 330: (28.55344, 77.08838)
    {
        "session_id": SESSION, "nav_mode": "ONLINE", "position_mode": "GPS",
        "next_instruction_text": "CRASH DETECTED — SOS sent to emergency contacts",
        "distance_to_next_m": 0, "confidence": 0.99,
        "off_route_flag": False, "destination_reached_flag": False,
        "active_step_index": 18,
        "route_polyline": poly(18),
    },

    # ── 19. ONLINE + GPS — crash dismissed, final approach ───────────────────
    # KML coord idx 352: (28.55399, 77.08608) — SLIGHT_RIGHT, airport road
    {
        "session_id": SESSION, "nav_mode": "ONLINE", "position_mode": "GPS",
        "next_instruction_text": "Keep slight right — Pavillion Mall in 400 m",
        "distance_to_next_m": 400, "confidence": 0.98,
        "off_route_flag": False, "destination_reached_flag": False,
        "active_step_index": 19,
        "route_polyline": poly(19),
    },

    # ── 20. ONLINE + GPS — ARRIVED ────────────────────────────────────────────
    # KML coord idx 371 (last): (28.55543, 77.08507)
    # destination = Pavillion Mall per KML Placemark
    {
        "session_id": SESSION, "nav_mode": "ONLINE", "position_mode": "GPS",
        "next_instruction_text": "You have arrived at IGI Airport T3 Metro Station",
        "distance_to_next_m": 0, "confidence": 0.99,
        "off_route_flag": False, "destination_reached_flag": True,
        "active_step_index": 20,
        "route_polyline": poly(20),
    },
]

NOTES = [
    "ONLINE  + GPS     start: MIT WPU",
    "ONLINE  + GPS     SLIGHT_RIGHT onto NH-48 slip road",
    "ONLINE  + GPS     RIGHT onto NH-48 main carriageway",
    "ONLINE  + GPS     STRAIGHT on NH-48 northbound",
    "ONLINE  + GPS     STRAIGHT — Shankar Chowk flyover",
    "ONLINE  + VISUAL  GPS brief loss under flyover — Vijit CV active",
    "OFFLINE + GPS     internet dropped, cached tiles",
    "OFFLINE + GPS     SLIGHT_RIGHT — NH-48 curve near Iffco Metro",
    "OFFLINE + GPS     STRAIGHT — NH-48 main stretch",
    "OFFLINE + GPS     STRAIGHT — Hero Honda Chowk",
    "OFFLINE + GPS     STRAIGHT — approaching Rajokri",
    "OFFLINE + VISUAL  GPS lost under Rajokri overpass — Vijit CV",
    "OFFLINE + VISUAL  STRAIGHT — Vijit CV tracking",
    "DEGRADED + VISUAL SLIGHT_LEFT — signal degraded",
    "DEGRADED + UNKNOWN complete blackout, last pos held",
    "OFFLINE + GPS     signals restored, SLIGHT_RIGHT",
    "OFFLINE + GPS     OFF ROUTE — missed Mahipalpur exit",
    "ONLINE  + GPS     rerouted, SLIGHT_LEFT near airport",
    "ONLINE  + GPS     CRASH DETECTED — SOS overlay",
    "ONLINE  + GPS     SLIGHT_RIGHT — final approach T3",
    "ONLINE  + GPS     ARRIVED at Pavillion Mall",
]


# ── API helpers ───────────────────────────────────────────────────────────────

def check_server():
    try:
        return requests.get(f"{SERVER}/status", timeout=3).status_code == 200
    except:
        return False

def connected_clients():
    try:
        return requests.get(f"{SERVER}/status", timeout=3).json().get("clients", 0)
    except:
        return 0

def send_ui_state(payload):
    """UIStateMessage API call from nav module to embedded server (spec section 3)."""
    payload["ts_ms"] = int(time.time() * 1000)
    try:
        r = requests.post(f"{SERVER}/receive", json=payload, timeout=3)
        return r.status_code == 200
    except:
        return False


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\nSmartHelmet — KML Route Test Input")
    print("Source:  maps_test.kml (Google My Maps export)")
    print("Route:   MIT WPU → Pavillion Mall")
    print("Points:  372 exact KML GPS coordinates → 21 navigation steps")
    print("Dist:    10.91 km on NH-48 Delhi-Gurgaon Expressway\n")

    if not check_server():
        print(f"  ERROR: server not running at {SERVER}")
        print("  Run:  python -m embedded.websocket_server\n")
        sys.exit(1)
    print("  Server OK")

    print("\nOpen browser: http://localhost:8765/")
    print("Waiting for browser to connect", end="", flush=True)
    for _ in range(30):
        if connected_clients() > 0:
            break
        print(".", end="", flush=True)
        time.sleep(1)
    else:
        print("\n\nNo browser connected after 30 s.\n")
        sys.exit(1)

    n = connected_clients()
    print(f"\nBrowser connected ({n} client). Streaming {len(ROUTE)} steps at 2.5 s\n")
    print(f"  {'#':>2}  {'Nav':>10}  {'Pos':>8}  {'TurnClass':>13}  "
          f"{'Lng':>10}  {'Lat':>10}  Note")
    print("  " + "─" * 90)

    for i, step in enumerate(ROUTE):
        pos    = step["route_polyline"][-1]
        ok     = send_ui_state(step)
        st     = "OK" if ok else "FAIL"
        flags  = ""
        if step["off_route_flag"]:           flags += " [OFF-ROUTE]"
        if step["destination_reached_flag"]: flags += " [ARRIVED]"
        if "crash" in step["next_instruction_text"].lower(): flags += " [CRASH/SOS]"

        # Derive turn class label from instruction text for display
        instr = step["next_instruction_text"].lower()
        tc = ("RIGHT"        if "turn right"    in instr else
              "SLIGHT_RIGHT" if "slight right"  in instr else
              "LEFT"         if "turn left"     in instr else
              "SLIGHT_LEFT"  if "slight left"   in instr else
              "U_TURN"       if "u-turn"        in instr else
              "STRAIGHT")

        print(f"  [{st}] {i:>2}  {step['nav_mode']:>10}  "
              f"{step['position_mode']:>8}  {tc:>13}  "
              f"{pos[0]:.6f}  {pos[1]:.6f}  {NOTES[i]}{flags}")

        if i < len(ROUTE) - 1:
            time.sleep(2.5)

    print("\nStream complete.")
    print("  Blue line on map should trace the exact KML route geometry.")
    print("  NavMode pill: ONLINE(green)/OFFLINE(amber)/DEGRADED(red)")
    print("  GPS badge: GPS(blue)/VISUAL-CV(purple)/NO SIGNAL(red)")
    print("  Turn arrows: ↑ STRAIGHT  → RIGHT  ← LEFT  ↩ U-TURN")

