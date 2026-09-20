FRACFOCUS DATA DICTIONARY - Last updated: November 2023
--------------------------------------------------------
This data dictionary defines the columns for files in the FracFocus CSV download. This download includes all availalbe Data that can be found by searching at: https://fracfocus.org/wells


File Name: DisclosureList_#.csv
--------------------------
DisclosureId - Key index for the Disclosure data.

JobStartDate - The date on which the hydraulic fracturing job was initiated.  Does not include site preparation or setup.

JobEndDate - The date on which the hydraulic fracturing job was completed.  Does not include site teardown.

APINumber - The American Petroleum Institute well identification number formatted as follows xx-xxx-xxxxx-00-00 Where: First two digits 
represent the state, second three digits represent the county, third 5 digits represent the well.

StateName - The name of the state where the surface location of the well resides.  Calculated from the API number.

CountyName - The name of the county were the surface location of the well resides.  Calculated from the API number.

OperatorName - The Operator Name of Organization submitting in FracFocus.

WellName - The name of the well.

Latitude - The lines that circle the earth horizontally, running side to side at equal distances apart on the earth.   Latitude is typically 
expressed in degrees North/ South.  In the FracFocus system these lines are shown in decimal degrees and must be between 15 and 75.

Longitude - The lines that circle the earth vertically, running top to bottom that are equal distances apart at the equator 
and merge at the geographic top and bottom of the earth.  Longitude is typically expressed in degrees East/ West.  In the FracFocus 
system the number representing these  lines are shown in decimal degrees and must be between -180 and -163 Note: Longitude number must 
be preceded by a negative sign.

Projection - The geographic coordinate system to which the latitude and longitude are related. In the FracFocus 
system the projection systems allowed are NAD (North American Datum) 27 or 83 and World Geodetic System 1984 (WGS84).

TVD - The vertical distance from a point in the well (usually the current or final depth) to a point at the surface, usually the 
elevation of the rotary kelly bushing.

TotalBaseWaterVolume - The total volume of water used as a carrier fluid for the hydraulic fracturing job (in gallons).

TotalBaseNonWaterVolume - The total volume of non water components used as a carrier fluid for the hydraulic fracturing job (in gallons)

FFVersion - A key which designates which version of FracFocus was used when the disclosure was submitted.

FederalWell - True = Yes, False = No. - Well is associated with Federal Land or Minerals.

IndianWell - True = Yes, False = No. - Well is associated with Tribal Land or Minerals.


File Name: FracFocusRegistry_#.csv
---------------------------------
DisclosureId - Key index for the Disclosure data.

JobStartDate - The date on which the hydraulic fracturing job was initiated.  Does not include site preparation or setup.

JobEndDate - The date on which the hydraulic fracturing job was completed.  Does not include site teardown.

APINumber - The American Petroleum Institute well identification number formatted as follows xx-xxx-xxxxx-00-00 Where: First two digits 
represent the state, second three digits represent the county, third 5 digits represent the well.

StateName - The name of the state where the surface location of the well resides.  Calculated from the API number.

CountyName - The name of the county were the surface location of the well resides.  Calculated from the API number.

OperatorName - The Operator Name of Organization submitting in FracFocus.

WellName - The name of the well.

Latitude - The lines that circle the earth horizontally, running side to side at equal distances apart on the earth.   Latitude is typically 
expressed in degrees North/ South.  In the FracFocus system these lines are shown in decimal degrees and must be between 15 and 75.

Longitude - The lines that circle the earth vertically, running top to bottom that are equal distances apart at the equator 
and merge at the geographic top and bottom of the earth.  Longitude is typically expressed in degrees East/ West.  In the FracFocus 
system the number representing these  lines are shown in decimal degrees and must be between -180 and -163 Note: Longitude number must 
be preceded by a negative sign.

Projection - The geographic coordinate system to which the latitude and longitude are related. In the FracFocus 
system the projection systems allowed are NAD (North American Datum) 27 or 83 and World Geodetic System 1984 (WGS84).

TVD - The vertical distance from a point in the well (usually the current or final depth) to a point at the surface, usually the 
elevation of the rotary kelly bushing.

TotalBaseWaterVolume - The total volume of water used as a carrier fluid for the hydraulic fracturing job (in gallons).

TotalBaseNonWaterVolume - The total volume of non water components used as a carrier fluid for the hydraulic fracturing job (in gallons)

FFVersion - A key which designates which version of FracFocus was used when the disclosure was submitted.

FederalWell - True = Yes, False = No. - Well is associated with Federal Land or Minerals.

IndianWell - True = Yes, False = No. - Well is associated with Tribal Land or Minerals.

PurposeId - Key index for the Purpose data.

TradeName - The name of the product as defined by the supplier.

Supplier - The name of the company that supplied the product for the hydraulic fracturing job (Usually the service company).

Purpose - The reason the product was used (e.g. Surfactant, Biocide, Proppant, etc.).

IngredientsId - Key index for the Ingredients data.

CASNumber - The Chemical Abstract Service identification number.

IngredientName - Name of the chemical or for Trade Secret chemicals the chemical family name.

IngredientCommonName - Common Name of the chemical based on submission frequency in FracFocus. 

PercentHighAdditive - The percent of the ingredient in the Trade Name product in % (Top of the range from MSDS).

PercentHFJob - The amount of the ingredient in the total hydraulic fracturing volume in % by Mass.

IngredientComment - Any comments related to the specific ingredient.

IngredientMSDS - True = Yes, False = No. - Is ingredient listed on MSDS sheet.

MassIngredient - Mass in pounds of the ingredient used on Job.

ClaimantCompany - Name of company claiming trade secret on ingredient.


File Name: WaterSource_#.csv
-------------------------------------
WaterSourceId - Key index for the WaterSource data.

DisclosureId - Foreign key linking to the Disclosure data.

APINumber - The American Petroleum Institute well identification number formatted as follows xx-xxx-xxxxx-00-00 Where: First two digits 
represent the state, second three digits represent the county, third 5 digits represent the well.

StateName - The name of the state where the surface location of the well resides.  Calculated from the API number.

CountyName - The name of the county were the surface location of the well resides.  Calculated from the API number.

OperatorName - The Operator Name of Organization submitting in FracFocus.

WellName - The name of the well.

Description - Definition of Water Source used on Job.

Percent - Percent of water defined in Description used on Job.