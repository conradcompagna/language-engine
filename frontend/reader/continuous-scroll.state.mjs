/** Mutable feature state; initialized explicitly by the ordered bootstrap. */
export const continuousScrollState = {
  docNavDragging: undefined,
  docNavHoldDirection: undefined,
  docNavHoldUnit: undefined,
  docNavHoldDelayTimer: undefined,
  docNavHoldRepeatTimer: undefined,
  docNavHoldDidRepeat: undefined,
  docNavHoldPointerId: undefined,
  docNavDragOffsetY: undefined,
  docNavDragPreviewPageIndex: undefined,
  docNavNativePreviewRatio: undefined,
  docNavFoliateInteractionActive: undefined,
  docNavFoliateRenderInFlight: undefined,
  docNavFoliateRenderTargetPage: undefined,
  docNavFoliateRenderFrame: undefined
};
