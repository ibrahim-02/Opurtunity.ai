/*************************************************************************
* ADOBE CONFIDENTIAL
* ___________________
*
*  Copyright 2015 Adobe Systems Incorporated
*  All Rights Reserved.
*
* NOTICE:  All information contained herein is, and remains
* the property of Adobe Systems Incorporated and its suppliers,
* if any.  The intellectual and technical concepts contained
* herein are proprietary to Adobe Systems Incorporated and its
* suppliers and are protected by all applicable intellectual property laws,
* including trade secret and or copyright laws.
* Dissemination of this information or reproduction of this material
* is strictly forbidden unless prior written permission is obtained
* from Adobe Systems Incorporated.
**************************************************************************/
import{floodgate as t}from"../floodgate.js";import{util as e}from"../util.js";import{setExperimentCodeForAnalytics as o,removeExperimentCodeForAnalytics as n}from"../../common/experimentUtils.js";import{checkUserLocaleEnabled as r,safeParseFeatureFlag as a}from"../gsuite/util.js";import{TOUCHPOINT_REGISTRY as i}from"./touchpoint-registry.js";const c=["treatmentFlag","surface","verb","translations","promotionSourcePrefix","promotionSourceSuffix"];export function createTouchpointInit(l){const s=i[l];if(!s)throw new Error(`Unknown touchpoint: ${l}`);return function(t,e){const o=c.find(t=>!e[t]);if(o)throw new Error(`Touchpoint "${t}" missing required field: ${o}`)}(l,s),async function(i){const c=[t.hasFlag(s.treatmentFlag),t.hasFlag(s.controlFlag)];s.fteFlag&&c.push(t.hasFlag(s.fteFlag));const l=await Promise.all(c),f=l[0],u=l[1],p=!!s.fteFlag&&l[2];let g;g=f?a(s.treatmentFlag):u?a(s.controlFlag):{},function(t){return!t||void 0===t.enLocaleEnabled&&void 0===t.nonEnLocaleEnabled}(g)&&s.devConfig&&(g={...s.devConfig,...g});const m=r(g?.enLocaleEnabled,g?.nonEnLocaleEnabled),d=!!s.preferenceKey&&!e.isAcrobatTouchPointEnabled(s.preferenceKey),h=f&&m&&!d,T=u&&m&&!d;h?(n(s.controlCode),o(s.treatmentCode)):T?(n(s.treatmentCode),o(s.controlCode)):(n(s.treatmentCode),n(s.controlCode));const F=g?.fileTypes||s.fileTypeMetadataFlags||[],y=F.length>0?await async function(e,o){const n=[];let r={};const a=e.map(async e=>{const a=`dc-cv-${o}-${e}-metadata`;if(!await t.hasFlag(a))return;const i=t.getFeatureMeta(a);if(!i)return;let c;try{c=JSON.parse(i)}catch(t){return}c?.selectors?.forEach(t=>n.push(t)),r={...r,...c?.types}});return await Promise.all(a),{selectors:n,fileExtToMimeTypeMap:r}}(F,s.surface):{};let b={};s.fteFlag&&p&&(b=a(s.fteFlag));const S=s.translations||{},x={};S.fteTitle&&(x.title=e.getTranslation(S.fteTitle)),S.fteDescription&&(x.description=e.getTranslation(S.fteDescription)),S.closeButton&&(x.button=e.getTranslation(S.closeButton));i({enabled:h,controlEnabled:T,metadata:y,touchpointConfig:g,touchPointText:S.touchPointText?e.getTranslation(S.touchPointText):"",fteTooltipStrings:x,enableFte:p&&m,fteConfig:b,verb:s.verb,surface:s.surface,promotionSourcePrefix:s.promotionSourcePrefix,promotionSourceSuffix:s.promotionSourceSuffix,fteStorageKey:s.fteStorageKey,fteType:s.fteType})}}