/**
 * Demo route data — DLF CyberHub, Gurgaon → IGI Airport T3 Metro Station, Delhi
 *
 * Ported from embedded/test_input.py (372 KML GPS points, 21 navigation steps).
 * Covers all sensor/connectivity mode combinations:
 *   ONLINE+GPS, ONLINE+VISUAL, OFFLINE+GPS, OFFLINE+VISUAL,
 *   DEGRADED+VISUAL, DEGRADED+UNKNOWN, crash event, off-route event, arrival.
 *
 * Total route: ~10.91 km on NH-48 Delhi-Gurgaon Expressway.
 */

export type NavMode = 'ONLINE' | 'OFFLINE' | 'DEGRADED';
export type PositionMode = 'GPS' | 'VISUAL' | 'UNKNOWN';

export interface LatLon {
  lat: number;
  lon: number;
}

export interface DemoStep {
  sessionId: string;
  navMode: NavMode;
  positionMode: PositionMode;
  nextInstructionText: string;
  distanceToNextM: number;
  confidence: number;
  offRoute: boolean;
  destinationReached: boolean;
  activeStepIndex: number;
  /** Growing polyline — the "trail" of the route up to this step. */
  routePolyline: LatLon[];
  /** Current rider position is the last point in routePolyline. */
}

// ── Full 372-point polyline from KML ─────────────────────────────────────────
// Every coordinate is [lat, lon] directly from maps_test.kml LineString.
const _FULL: [number, number][] = [
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
];

// KML waypoint indices — which point in _FULL marks the end of each step
const _IDX = [0, 6, 34, 40, 75, 85, 105, 130, 150, 165, 185, 200, 215, 224, 245, 270, 295, 316, 330, 352, 371];

function poly(stepNum: number): LatLon[] {
  return _FULL.slice(0, _IDX[stepNum] + 1).map(([lat, lon]) => ({lat, lon}));
}

export const DEMO_SESSION_ID = 'ride_cyberhub_igi_001';
export const DEMO_ORIGIN: LatLon = {lat: 28.49541, lon: 77.08937}; // DLF CyberHub
export const DEMO_DEST: LatLon = {lat: 28.55543, lon: 77.08507};   // IGI T3 Metro
export const FULL_POLYLINE: LatLon[] = _FULL.map(([lat, lon]) => ({lat, lon}));

/** Time each step is displayed (milliseconds). Adjust for faster/slower playback. */
export const STEP_INTERVAL_MS = 3000;

export const DEMO_STEPS: DemoStep[] = [
  {
    sessionId: DEMO_SESSION_ID, navMode: 'ONLINE', positionMode: 'GPS',
    nextInstructionText: 'Head north-east from DLF CyberHub',
    distanceToNextM: 373, confidence: 0.97,
    offRoute: false, destinationReached: false, activeStepIndex: 0,
    routePolyline: poly(0),
  },
  {
    sessionId: DEMO_SESSION_ID, navMode: 'ONLINE', positionMode: 'GPS',
    nextInstructionText: 'Keep slight right onto NH-48 slip road',
    distanceToNextM: 195, confidence: 0.96,
    offRoute: false, destinationReached: false, activeStepIndex: 1,
    routePolyline: poly(1),
  },
  {
    sessionId: DEMO_SESSION_ID, navMode: 'ONLINE', positionMode: 'GPS',
    nextInstructionText: 'Turn right onto NH-48 Delhi-Gurgaon Expressway',
    distanceToNextM: 603, confidence: 0.97,
    offRoute: false, destinationReached: false, activeStepIndex: 2,
    routePolyline: poly(2),
  },
  {
    sessionId: DEMO_SESSION_ID, navMode: 'ONLINE', positionMode: 'GPS',
    nextInstructionText: 'Continue straight on NH-48 Expressway',
    distanceToNextM: 602, confidence: 0.97,
    offRoute: false, destinationReached: false, activeStepIndex: 3,
    routePolyline: poly(3),
  },
  {
    sessionId: DEMO_SESSION_ID, navMode: 'ONLINE', positionMode: 'GPS',
    nextInstructionText: 'Continue straight — Shankar Chowk flyover ahead',
    distanceToNextM: 626, confidence: 0.96,
    offRoute: false, destinationReached: false, activeStepIndex: 4,
    routePolyline: poly(4),
  },
  {
    sessionId: DEMO_SESSION_ID, navMode: 'ONLINE', positionMode: 'VISUAL',
    nextInstructionText: 'Continue straight — GPS brief loss under flyover',
    distanceToNextM: 640, confidence: 0.83,
    offRoute: false, destinationReached: false, activeStepIndex: 5,
    routePolyline: poly(5),
  },
  {
    sessionId: DEMO_SESSION_ID, navMode: 'OFFLINE', positionMode: 'GPS',
    nextInstructionText: 'Continue straight — offline maps active',
    distanceToNextM: 610, confidence: 0.94,
    offRoute: false, destinationReached: false, activeStepIndex: 6,
    routePolyline: poly(6),
  },
  {
    sessionId: DEMO_SESSION_ID, navMode: 'OFFLINE', positionMode: 'GPS',
    nextInstructionText: 'Keep slight right on NH-48',
    distanceToNextM: 711, confidence: 0.93,
    offRoute: false, destinationReached: false, activeStepIndex: 7,
    routePolyline: poly(7),
  },
  {
    sessionId: DEMO_SESSION_ID, navMode: 'OFFLINE', positionMode: 'GPS',
    nextInstructionText: 'Continue straight on NH-48',
    distanceToNextM: 618, confidence: 0.92,
    offRoute: false, destinationReached: false, activeStepIndex: 8,
    routePolyline: poly(8),
  },
  {
    sessionId: DEMO_SESSION_ID, navMode: 'OFFLINE', positionMode: 'GPS',
    nextInstructionText: 'Continue straight — Hero Honda Chowk flyover',
    distanceToNextM: 654, confidence: 0.91,
    offRoute: false, destinationReached: false, activeStepIndex: 9,
    routePolyline: poly(9),
  },
  {
    sessionId: DEMO_SESSION_ID, navMode: 'OFFLINE', positionMode: 'GPS',
    nextInstructionText: 'Continue straight — approaching Rajokri',
    distanceToNextM: 617, confidence: 0.90,
    offRoute: false, destinationReached: false, activeStepIndex: 10,
    routePolyline: poly(10),
  },
  {
    sessionId: DEMO_SESSION_ID, navMode: 'OFFLINE', positionMode: 'VISUAL',
    nextInstructionText: 'Continue straight — CV localization active',
    distanceToNextM: 622, confidence: 0.76,
    offRoute: false, destinationReached: false, activeStepIndex: 11,
    routePolyline: poly(11),
  },
  {
    sessionId: DEMO_SESSION_ID, navMode: 'OFFLINE', positionMode: 'VISUAL',
    nextInstructionText: 'Continue straight on NH-48 — Vijit CV tracking',
    distanceToNextM: 603, confidence: 0.71,
    offRoute: false, destinationReached: false, activeStepIndex: 12,
    routePolyline: poly(12),
  },
  {
    sessionId: DEMO_SESSION_ID, navMode: 'DEGRADED', positionMode: 'VISUAL',
    nextInstructionText: 'Keep slight left — signal degraded, CV only',
    distanceToNextM: 615, confidence: 0.56,
    offRoute: false, destinationReached: false, activeStepIndex: 13,
    routePolyline: poly(13),
  },
  {
    sessionId: DEMO_SESSION_ID, navMode: 'DEGRADED', positionMode: 'UNKNOWN',
    nextInstructionText: 'Signal lost — holding last known position',
    distanceToNextM: 1800, confidence: 0.21,
    offRoute: false, destinationReached: false, activeStepIndex: 14,
    routePolyline: poly(13), // position held at last known point
  },
  {
    sessionId: DEMO_SESSION_ID, navMode: 'OFFLINE', positionMode: 'GPS',
    nextInstructionText: 'Keep slight right — route recalculated',
    distanceToNextM: 605, confidence: 0.91,
    offRoute: false, destinationReached: false, activeStepIndex: 15,
    routePolyline: poly(15),
  },
  {
    sessionId: DEMO_SESSION_ID, navMode: 'OFFLINE', positionMode: 'GPS',
    nextInstructionText: 'Off route — recalculating',
    distanceToNextM: 0, confidence: 0.52,
    offRoute: true, destinationReached: false, activeStepIndex: 16,
    routePolyline: poly(16),
  },
  {
    sessionId: DEMO_SESSION_ID, navMode: 'ONLINE', positionMode: 'GPS',
    nextInstructionText: 'Keep slight left — rerouted to IGI T3',
    distanceToNextM: 613, confidence: 0.96,
    offRoute: false, destinationReached: false, activeStepIndex: 17,
    routePolyline: poly(17),
  },
  {
    sessionId: DEMO_SESSION_ID, navMode: 'ONLINE', positionMode: 'GPS',
    nextInstructionText: 'CRASH DETECTED — SOS sent to emergency contacts',
    distanceToNextM: 0, confidence: 0.99,
    offRoute: false, destinationReached: false, activeStepIndex: 18,
    routePolyline: poly(18),
  },
  {
    sessionId: DEMO_SESSION_ID, navMode: 'ONLINE', positionMode: 'GPS',
    nextInstructionText: 'Keep slight right — IGI T3 Metro Station in 400 m',
    distanceToNextM: 400, confidence: 0.98,
    offRoute: false, destinationReached: false, activeStepIndex: 19,
    routePolyline: poly(19),
  },
  {
    sessionId: DEMO_SESSION_ID, navMode: 'ONLINE', positionMode: 'GPS',
    nextInstructionText: 'You have arrived at IGI Airport T3 Metro Station',
    distanceToNextM: 0, confidence: 0.99,
    offRoute: false, destinationReached: true, activeStepIndex: 20,
    routePolyline: poly(20),
  },
];
