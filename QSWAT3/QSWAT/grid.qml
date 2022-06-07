<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>
<qgis minScale="100000000" version="3.16.8-Hannover" simplifyDrawingTol="1" readOnly="0" simplifyDrawingHints="1" hasScaleBasedVisibilityFlag="0" labelsEnabled="0" simplifyAlgorithm="0" simplifyLocal="1" simplifyMaxScale="1" styleCategories="AllStyleCategories" maxScale="0">
  <flags>
    <Identifiable>1</Identifiable>
    <Removable>1</Removable>
    <Searchable>1</Searchable>
  </flags>
  <temporal fixedDuration="0" durationField="" endExpression="" accumulate="0" enabled="0" endField="" durationUnit="min" mode="0" startField="" startExpression="">
    <fixedRange>
      <start></start>
      <end></end>
    </fixedRange>
  </temporal>
  <renderer-v2 forceraster="0" symbollevels="0" enableorderby="0" type="singleSymbol">
    <symbols>
      <symbol alpha="1" name="0" clip_to_extent="1" force_rhr="0" type="fill">
        <layer enabled="1" pass="0" locked="0" class="SimpleFill">
          <prop v="3x:0,0,0,0,0,0" k="border_width_map_unit_scale"/>
          <prop v="32,37,161,255" k="color"/>
          <prop v="bevel" k="joinstyle"/>
          <prop v="0,0" k="offset"/>
          <prop v="3x:0,0,0,0,0,0" k="offset_map_unit_scale"/>
          <prop v="MM" k="offset_unit"/>
          <prop v="255,0,0,255" k="outline_color"/>
          <prop v="solid" k="outline_style"/>
          <prop v="0.06" k="outline_width"/>
          <prop v="MM" k="outline_width_unit"/>
          <prop v="no" k="style"/>
          <data_defined_properties>
            <Option type="Map">
              <Option value="" name="name" type="QString"/>
              <Option name="properties"/>
              <Option value="collection" name="type" type="QString"/>
            </Option>
          </data_defined_properties>
        </layer>
      </symbol>
    </symbols>
    <rotation/>
    <sizescale/>
  </renderer-v2>
  <labeling type="simple">
    <settings calloutType="simple">
      <text-style textOrientation="horizontal" fontKerning="1" blendMode="0" fontSizeUnit="Point" namedStyle="Normal" fontFamily="MS Shell Dlg 2" capitalization="0" textOpacity="1" fontLetterSpacing="0" textColor="0,0,0,255" fontWordSpacing="0" fieldName="CASE WHEN &quot;Subbasin&quot; = 0 THEN '' ELSE &quot;Subbasin&quot; END" multilineHeight="1" fontItalic="0" allowHtml="0" fontUnderline="0" fontSize="8.25" useSubstitutions="0" fontSizeMapUnitScale="3x:0,0,0,0,0,0" fontWeight="50" fontStrikeout="0" previewBkgrdColor="255,255,255,255" isExpression="1">
        <text-buffer bufferNoFill="0" bufferSizeUnits="MM" bufferColor="255,255,255,255" bufferOpacity="1" bufferSizeMapUnitScale="3x:0,0,0,0,0,0" bufferBlendMode="0" bufferJoinStyle="64" bufferDraw="0" bufferSize="1"/>
        <text-mask maskType="0" maskSizeMapUnitScale="3x:0,0,0,0,0,0" maskEnabled="0" maskSize="1.5" maskSizeUnits="MM" maskJoinStyle="128" maskOpacity="1" maskedSymbolLayers=""/>
        <background shapeOffsetMapUnitScale="3x:0,0,0,0,0,0" shapeSizeX="0" shapeOpacity="1" shapeSizeY="0" shapeJoinStyle="64" shapeRadiiX="0" shapeRadiiMapUnitScale="3x:0,0,0,0,0,0" shapeBorderColor="128,128,128,255" shapeRadiiY="0" shapeBorderWidth="0" shapeBorderWidthUnit="MM" shapeFillColor="255,255,255,255" shapeDraw="0" shapeOffsetY="0" shapeRotation="0" shapeRadiiUnit="MM" shapeSizeType="0" shapeRotationType="0" shapeType="0" shapeBlendMode="0" shapeSizeMapUnitScale="3x:0,0,0,0,0,0" shapeOffsetX="0" shapeBorderWidthMapUnitScale="3x:0,0,0,0,0,0" shapeOffsetUnit="MM" shapeSizeUnit="MM" shapeSVGFile=""/>
        <shadow shadowRadius="1.5" shadowScale="100" shadowRadiusMapUnitScale="3x:0,0,0,0,0,0" shadowOpacity="0.7" shadowRadiusUnit="MM" shadowDraw="0" shadowOffsetDist="1" shadowRadiusAlphaOnly="0" shadowOffsetAngle="135" shadowColor="0,0,0,255" shadowOffsetUnit="MM" shadowOffsetGlobal="1" shadowUnder="0" shadowOffsetMapUnitScale="3x:0,0,0,0,0,0" shadowBlendMode="6"/>
        <dd_properties>
          <Option type="Map">
            <Option value="" name="name" type="QString"/>
            <Option name="properties"/>
            <Option value="collection" name="type" type="QString"/>
          </Option>
        </dd_properties>
        <substitutions/>
      </text-style>
      <text-format addDirectionSymbol="0" rightDirectionSymbol=">" formatNumbers="0" plussign="0" reverseDirectionSymbol="0" useMaxLineLengthForAutoWrap="1" autoWrapLength="0" leftDirectionSymbol="&lt;" wrapChar="" multilineAlign="0" decimals="3" placeDirectionSymbol="0"/>
      <placement rotationAngle="0" dist="0" xOffset="0" geometryGenerator="" overrunDistance="0" lineAnchorPercent="0.5" maxCurvedCharAngleIn="20" repeatDistanceMapUnitScale="3x:0,0,0,0,0,0" predefinedPositionOrder="TR,TL,BR,BL,R,L,TSR,BSR" fitInPolygonOnly="0" labelOffsetMapUnitScale="3x:0,0,0,0,0,0" priority="5" layerType="UnknownGeometry" geometryGeneratorType="PointGeometry" placementFlags="0" geometryGeneratorEnabled="0" repeatDistance="0" offsetType="0" distUnits="MM" placement="1" overrunDistanceUnit="MM" lineAnchorType="0" centroidInside="1" offsetUnits="MapUnit" maxCurvedCharAngleOut="-20" overrunDistanceMapUnitScale="3x:0,0,0,0,0,0" quadOffset="4" centroidWhole="1" preserveRotation="1" repeatDistanceUnits="MM" distMapUnitScale="3x:0,0,0,0,0,0" yOffset="0" polygonPlacementFlags="2"/>
      <rendering mergeLines="0" fontMaxPixelSize="10000" obstacleFactor="1" obstacleType="0" scaleMin="1" scaleVisibility="0" labelPerPart="0" minFeatureSize="0" displayAll="0" zIndex="0" drawLabels="1" scaleMax="10000000" fontMinPixelSize="3" upsidedownLabels="0" limitNumLabels="0" fontLimitPixelSize="0" obstacle="1" maxNumLabels="2000"/>
      <dd_properties>
        <Option type="Map">
          <Option value="" name="name" type="QString"/>
          <Option name="properties"/>
          <Option value="collection" name="type" type="QString"/>
        </Option>
      </dd_properties>
      <callout type="simple">
        <Option type="Map">
          <Option value="pole_of_inaccessibility" name="anchorPoint" type="QString"/>
          <Option name="ddProperties" type="Map">
            <Option value="" name="name" type="QString"/>
            <Option name="properties"/>
            <Option value="collection" name="type" type="QString"/>
          </Option>
          <Option value="false" name="drawToAllParts" type="bool"/>
          <Option value="0" name="enabled" type="QString"/>
          <Option value="point_on_exterior" name="labelAnchorPoint" type="QString"/>
          <Option value="&lt;symbol alpha=&quot;1&quot; name=&quot;symbol&quot; clip_to_extent=&quot;1&quot; force_rhr=&quot;0&quot; type=&quot;line&quot;>&lt;layer enabled=&quot;1&quot; pass=&quot;0&quot; locked=&quot;0&quot; class=&quot;SimpleLine&quot;>&lt;prop v=&quot;0&quot; k=&quot;align_dash_pattern&quot;/>&lt;prop v=&quot;square&quot; k=&quot;capstyle&quot;/>&lt;prop v=&quot;5;2&quot; k=&quot;customdash&quot;/>&lt;prop v=&quot;3x:0,0,0,0,0,0&quot; k=&quot;customdash_map_unit_scale&quot;/>&lt;prop v=&quot;MM&quot; k=&quot;customdash_unit&quot;/>&lt;prop v=&quot;0&quot; k=&quot;dash_pattern_offset&quot;/>&lt;prop v=&quot;3x:0,0,0,0,0,0&quot; k=&quot;dash_pattern_offset_map_unit_scale&quot;/>&lt;prop v=&quot;MM&quot; k=&quot;dash_pattern_offset_unit&quot;/>&lt;prop v=&quot;0&quot; k=&quot;draw_inside_polygon&quot;/>&lt;prop v=&quot;bevel&quot; k=&quot;joinstyle&quot;/>&lt;prop v=&quot;60,60,60,255&quot; k=&quot;line_color&quot;/>&lt;prop v=&quot;solid&quot; k=&quot;line_style&quot;/>&lt;prop v=&quot;0.3&quot; k=&quot;line_width&quot;/>&lt;prop v=&quot;MM&quot; k=&quot;line_width_unit&quot;/>&lt;prop v=&quot;0&quot; k=&quot;offset&quot;/>&lt;prop v=&quot;3x:0,0,0,0,0,0&quot; k=&quot;offset_map_unit_scale&quot;/>&lt;prop v=&quot;MM&quot; k=&quot;offset_unit&quot;/>&lt;prop v=&quot;0&quot; k=&quot;ring_filter&quot;/>&lt;prop v=&quot;0&quot; k=&quot;tweak_dash_pattern_on_corners&quot;/>&lt;prop v=&quot;0&quot; k=&quot;use_custom_dash&quot;/>&lt;prop v=&quot;3x:0,0,0,0,0,0&quot; k=&quot;width_map_unit_scale&quot;/>&lt;data_defined_properties>&lt;Option type=&quot;Map&quot;>&lt;Option value=&quot;&quot; name=&quot;name&quot; type=&quot;QString&quot;/>&lt;Option name=&quot;properties&quot;/>&lt;Option value=&quot;collection&quot; name=&quot;type&quot; type=&quot;QString&quot;/>&lt;/Option>&lt;/data_defined_properties>&lt;/layer>&lt;/symbol>" name="lineSymbol" type="QString"/>
          <Option value="0" name="minLength" type="double"/>
          <Option value="3x:0,0,0,0,0,0" name="minLengthMapUnitScale" type="QString"/>
          <Option value="MM" name="minLengthUnit" type="QString"/>
          <Option value="0" name="offsetFromAnchor" type="double"/>
          <Option value="3x:0,0,0,0,0,0" name="offsetFromAnchorMapUnitScale" type="QString"/>
          <Option value="MM" name="offsetFromAnchorUnit" type="QString"/>
          <Option value="0" name="offsetFromLabel" type="double"/>
          <Option value="3x:0,0,0,0,0,0" name="offsetFromLabelMapUnitScale" type="QString"/>
          <Option value="MM" name="offsetFromLabelUnit" type="QString"/>
        </Option>
      </callout>
    </settings>
  </labeling>
  <customproperties>
    <property value="0" key="embeddedWidgets/count"/>
    <property key="variableNames"/>
    <property key="variableValues"/>
  </customproperties>
  <blendMode>0</blendMode>
  <featureBlendMode>0</featureBlendMode>
  <layerOpacity>1</layerOpacity>
  <SingleCategoryDiagramRenderer diagramType="Histogram" attributeLegend="1">
    <DiagramCategory lineSizeType="MM" backgroundColor="#ffffff" spacingUnit="MM" direction="0" scaleBasedVisibility="0" labelPlacementMethod="XHeight" barWidth="5" rotationOffset="270" minScaleDenominator="0" enabled="0" sizeType="MM" spacingUnitScale="3x:0,0,0,0,0,0" opacity="1" height="15" minimumSize="0" penWidth="0" width="15" showAxis="1" diagramOrientation="Up" penColor="#000000" spacing="5" sizeScale="3x:0,0,0,0,0,0" backgroundAlpha="255" penAlpha="255" maxScaleDenominator="1e+08" lineSizeScale="3x:0,0,0,0,0,0" scaleDependency="Area">
      <fontProperties style="" description="MS Shell Dlg 2,8.25,-1,5,50,0,0,0,0,0"/>
      <attribute color="#000000" field="" label=""/>
      <axisSymbol>
        <symbol alpha="1" name="" clip_to_extent="1" force_rhr="0" type="line">
          <layer enabled="1" pass="0" locked="0" class="SimpleLine">
            <prop v="0" k="align_dash_pattern"/>
            <prop v="square" k="capstyle"/>
            <prop v="5;2" k="customdash"/>
            <prop v="3x:0,0,0,0,0,0" k="customdash_map_unit_scale"/>
            <prop v="MM" k="customdash_unit"/>
            <prop v="0" k="dash_pattern_offset"/>
            <prop v="3x:0,0,0,0,0,0" k="dash_pattern_offset_map_unit_scale"/>
            <prop v="MM" k="dash_pattern_offset_unit"/>
            <prop v="0" k="draw_inside_polygon"/>
            <prop v="bevel" k="joinstyle"/>
            <prop v="35,35,35,255" k="line_color"/>
            <prop v="solid" k="line_style"/>
            <prop v="0.26" k="line_width"/>
            <prop v="MM" k="line_width_unit"/>
            <prop v="0" k="offset"/>
            <prop v="3x:0,0,0,0,0,0" k="offset_map_unit_scale"/>
            <prop v="MM" k="offset_unit"/>
            <prop v="0" k="ring_filter"/>
            <prop v="0" k="tweak_dash_pattern_on_corners"/>
            <prop v="0" k="use_custom_dash"/>
            <prop v="3x:0,0,0,0,0,0" k="width_map_unit_scale"/>
            <data_defined_properties>
              <Option type="Map">
                <Option value="" name="name" type="QString"/>
                <Option name="properties"/>
                <Option value="collection" name="type" type="QString"/>
              </Option>
            </data_defined_properties>
          </layer>
        </symbol>
      </axisSymbol>
    </DiagramCategory>
  </SingleCategoryDiagramRenderer>
  <DiagramLayerSettings dist="0" zIndex="0" linePlacementFlags="18" placement="1" priority="0" showAll="1" obstacle="0">
    <properties>
      <Option type="Map">
        <Option value="" name="name" type="QString"/>
        <Option name="properties"/>
        <Option value="collection" name="type" type="QString"/>
      </Option>
    </properties>
  </DiagramLayerSettings>
  <geometryOptions removeDuplicateNodes="0" geometryPrecision="0">
    <activeChecks/>
    <checkConfiguration type="Map">
      <Option name="QgsGeometryGapCheck" type="Map">
        <Option value="0" name="allowedGapsBuffer" type="double"/>
        <Option value="false" name="allowedGapsEnabled" type="bool"/>
        <Option value="" name="allowedGapsLayer" type="QString"/>
      </Option>
    </checkConfiguration>
  </geometryOptions>
  <legend type="default-vector"/>
  <referencedLayers/>
  <fieldConfiguration>
    <field configurationFlags="None" name="PolygonId">
      <editWidget type="TextEdit">
        <config>
          <Option/>
        </config>
      </editWidget>
    </field>
    <field configurationFlags="None" name="DownId">
      <editWidget type="TextEdit">
        <config>
          <Option/>
        </config>
      </editWidget>
    </field>
    <field configurationFlags="None" name="Area">
      <editWidget type="TextEdit">
        <config>
          <Option/>
        </config>
      </editWidget>
    </field>
    <field configurationFlags="None" name="Outlet">
      <editWidget type="TextEdit">
        <config>
          <Option/>
        </config>
      </editWidget>
    </field>
    <field configurationFlags="None" name="Subbasin">
      <editWidget type="Range">
        <config>
          <Option/>
        </config>
      </editWidget>
    </field>
  </fieldConfiguration>
  <aliases>
    <alias index="0" field="PolygonId" name=""/>
    <alias index="1" field="DownId" name=""/>
    <alias index="2" field="Area" name=""/>
    <alias index="3" field="Outlet" name=""/>
    <alias index="4" field="Subbasin" name=""/>
  </aliases>
  <defaults>
    <default expression="" applyOnUpdate="0" field="PolygonId"/>
    <default expression="" applyOnUpdate="0" field="DownId"/>
    <default expression="" applyOnUpdate="0" field="Area"/>
    <default expression="" applyOnUpdate="0" field="Outlet"/>
    <default expression="" applyOnUpdate="0" field="Subbasin"/>
  </defaults>
  <constraints>
    <constraint constraints="0" unique_strength="0" notnull_strength="0" field="PolygonId" exp_strength="0"/>
    <constraint constraints="0" unique_strength="0" notnull_strength="0" field="DownId" exp_strength="0"/>
    <constraint constraints="0" unique_strength="0" notnull_strength="0" field="Area" exp_strength="0"/>
    <constraint constraints="0" unique_strength="0" notnull_strength="0" field="Outlet" exp_strength="0"/>
    <constraint constraints="0" unique_strength="0" notnull_strength="0" field="Subbasin" exp_strength="0"/>
  </constraints>
  <constraintExpressions>
    <constraint exp="" field="PolygonId" desc=""/>
    <constraint exp="" field="DownId" desc=""/>
    <constraint exp="" field="Area" desc=""/>
    <constraint exp="" field="Outlet" desc=""/>
    <constraint exp="" field="Subbasin" desc=""/>
  </constraintExpressions>
  <expressionfields/>
  <attributeactions>
    <defaultAction value="{00000000-0000-0000-0000-000000000000}" key="Canvas"/>
  </attributeactions>
  <attributetableconfig actionWidgetStyle="dropDown" sortOrder="0" sortExpression="">
    <columns>
      <column hidden="0" name="PolygonId" type="field" width="-1"/>
      <column hidden="0" name="DownId" type="field" width="-1"/>
      <column hidden="0" name="Area" type="field" width="-1"/>
      <column hidden="0" name="Outlet" type="field" width="-1"/>
      <column hidden="0" name="Subbasin" type="field" width="-1"/>
      <column hidden="1" type="actions" width="-1"/>
    </columns>
  </attributetableconfig>
  <conditionalstyles>
    <rowstyles/>
    <fieldstyles/>
  </conditionalstyles>
  <storedexpressions/>
  <editform tolerant="1">.</editform>
  <editforminit/>
  <editforminitcodesource>0</editforminitcodesource>
  <editforminitfilepath></editforminitfilepath>
  <editforminitcode><![CDATA[# -*- coding: utf-8 -*-
"""
QGIS forms can have a Python function that is called when the form is
opened.

Use this function to add extra logic to your forms.

Enter the name of the function in the "Python Init function"
field.
An example follows:
"""
from qgis.PyQt.QtWidgets import QWidget

def my_form_open(dialog, layer, feature):
	geom = feature.geometry()
	control = dialog.findChild(QWidget, "MyLineEdit")
]]></editforminitcode>
  <featformsuppress>0</featformsuppress>
  <editorlayout>generatedlayout</editorlayout>
  <editable>
    <field name="Area" editable="1"/>
    <field name="DownId" editable="1"/>
    <field name="Outlet" editable="1"/>
    <field name="PolygonId" editable="1"/>
    <field name="Subbasin" editable="1"/>
  </editable>
  <labelOnTop>
    <field labelOnTop="0" name="Area"/>
    <field labelOnTop="0" name="DownId"/>
    <field labelOnTop="0" name="Outlet"/>
    <field labelOnTop="0" name="PolygonId"/>
    <field labelOnTop="0" name="Subbasin"/>
  </labelOnTop>
  <dataDefinedFieldProperties/>
  <widgets/>
  <previewExpression>"PolygonId"</previewExpression>
  <mapTip></mapTip>
  <layerGeometryType>2</layerGeometryType>
</qgis>
