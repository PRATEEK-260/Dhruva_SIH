// Line colours for map layers, chosen so no line borrows a verdict colour: green
// means Safe and amber means Caution everywhere else in DHRUVA.

/** INCOIS's own PFZ-line colour (its GeoServer legend for PFZ_Automation:pfzlines),
 * so a fisherman who knows INCOIS's maps recognises the lines. Drawn over a dark
 * casing to read on the light sea-floor map. */
export const PFZ_YELLOW = "#ffff00";
export const PFZ_CASING = "#0f2a36";

/** Maritime limits in magenta, as nautical charts draw them. Always dashed:
 * indicative, never legal. */
export const BOUNDARY_MAGENTA = "#b3127a";
