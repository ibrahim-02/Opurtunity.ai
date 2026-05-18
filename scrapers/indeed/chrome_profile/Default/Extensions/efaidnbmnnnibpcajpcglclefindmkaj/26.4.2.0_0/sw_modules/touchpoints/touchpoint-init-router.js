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
import{createTouchpointInit as t}from"./touchpoint-init-factory.js";import{TOUCHPOINT_REGISTRY as n}from"./touchpoint-registry.js";const o="unknown",i="pending",c="initialized",r={},e={},a={};Object.keys(n).forEach(n=>{r[n]=t(n),a[n]=i});export async function touchpointInitDispatch(t,n){const i=a[t]??o;i!==o?i!==c?await r[t](o=>{e[t]=o,a[t]=c,n(o)}):n(e[t]):n({enabled:!1,state:i,error:`Unknown touchpoint: ${t}`})}