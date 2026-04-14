/**
 * useTurnConfirmation  —  skeleton
 *
 * PURPOSE (to be implemented in Phase 7):
 *   Detect whether the rider has executed the expected maneuver by watching
 *   the dead-reckoning heading and position from useDeadReckoning.
 *
 *   When a turn is confirmed → fires onTurnConfirmed(stepIndex)
 *     → caller sends LED_OFF to helmet, advances its local step display
 *
 *   When a wrong turn is detected → fires onWrongTurn()
 *     → caller sends NOP + next instruction to helmet
 *
 * PENDING DECISIONS:
 *   - Heading change threshold for "turn confirmed" (candidate: 25–45 °)
 *   - Distance window within which the heading change must occur (candidate: 80 m)
 *   - Whether vision module events can override / accelerate confirmation
 *   - Debounce time to avoid false positives on curves
 *
 * Current state: interface-only stub. Returns { isMonitoring: false } always.
 * NavigationScreen falls back to active_step_index change from NCS polling
 * as the confirmation signal until this module is implemented.
 */

export interface TurnConfirmationCallbacks {
  /** Called when heading change confirms the expected maneuver was executed */
  onTurnConfirmed: (stepIndex: number) => void;
  /** Called when heading change contradicts the expected maneuver */
  onWrongTurn: () => void;
}

export interface TurnConfirmationState {
  isMonitoring: boolean;  // true when actively watching for a turn
}

/**
 * @param currentStepIndex - The active_step_index from UIStateMessage
 * @param expectedInstruction - next_instruction_text from UIStateMessage
 * @param headingDeg - Smoothed heading from useDeadReckoning (degrees)
 * @param _callbacks - onTurnConfirmed / onWrongTurn (unused until implemented)
 */
export function useTurnConfirmation(
  _currentStepIndex: number,
  _expectedInstruction: string,
  _headingDeg: number,
  _callbacks: TurnConfirmationCallbacks,
): TurnConfirmationState {
  // TODO Phase 7: subscribe to DR heading changes; compare against expected
  // maneuver direction; fire callbacks when threshold exceeded.
  return {isMonitoring: false};
}
