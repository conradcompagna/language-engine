/** Mutable feature state; initialized explicitly by the ordered bootstrap. */
export const hoverInteractionState = {
  fuzzyCache: undefined,
  cachedRowBands: undefined,
  cachedRowSnapPoints: undefined,
  cachedRowGapRanges: undefined,
  hoverRafId: undefined,
  pendingHoverEvent: undefined,
  lastHoverProcessTime: undefined,
  hoverThrottleMs: undefined
};
