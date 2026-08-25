/*!
 * Copyright (C) Microsoft Corporation. All rights reserved.
 * This file follows the Power Apps generated data-source contract.
 */
export interface Pvci_transcriptaccessrequestsBase {
  ownerid: string;
  owneridtype: string;
  pvci_accessstatus?: string;
  pvci_action?: string;
  pvci_correlationid?: string;
  pvci_elevationcleanupverified?: boolean;
  "pvci_EnvironmentInventoryId@odata.bind"?: string;
  pvci_environmentid?: string;
  pvci_environmenturl?: string;
  pvci_error?: string;
  pvci_evidence?: string;
  pvci_name: string;
  pvci_processedon?: string;
  pvci_processor?: string;
  pvci_requestedmode?: string;
  pvci_requestedon?: string;
  pvci_requestkey?: string;
  pvci_roleverified?: boolean;
  pvci_status?: string;
  pvci_transcriptaccessrequestid: string;
}

export interface Pvci_transcriptaccessrequests extends Pvci_transcriptaccessrequestsBase {
  createdbyname?: string;
  createdon?: string;
  modifiedon?: string;
  owneridname?: string;
  _pvci_environmentinventoryid_value?: string;
}