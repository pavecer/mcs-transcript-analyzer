/*!
 * Copyright (C) Microsoft Corporation. All rights reserved.
 * This file follows the Power Apps generated data-source contract.
 */
import type { GetEntityMetadataOptions, EntityMetadata } from '@microsoft/power-apps/data/metadata/dataverse';
import type { IGetOptions, IGetAllOptions } from '../models/CommonModels';
import type { IOperationResult } from '@microsoft/power-apps/data';
import type { Pvci_transcriptaccessrequestsBase, Pvci_transcriptaccessrequests } from '../models/Pvci_transcriptaccessrequestsModel';
import { dataSourcesInfo } from '../../../.power/schemas/appschemas/dataSourcesInfo';
import { getClient } from '@microsoft/power-apps/data';

export class Pvci_transcriptaccessrequestsService {
  private static readonly dataSourceName = 'pvci_transcriptaccessrequests';
  private static readonly client = getClient(dataSourcesInfo);

  public static async create(record: Omit<Pvci_transcriptaccessrequestsBase, 'pvci_transcriptaccessrequestid'>): Promise<IOperationResult<Pvci_transcriptaccessrequests>> {
    return Pvci_transcriptaccessrequestsService.client.createRecordAsync<Omit<Pvci_transcriptaccessrequestsBase, 'pvci_transcriptaccessrequestid'>, Pvci_transcriptaccessrequests>(
      Pvci_transcriptaccessrequestsService.dataSourceName,
      record
    );
  }

  public static async update(id: string, changedFields: Partial<Omit<Pvci_transcriptaccessrequestsBase, 'pvci_transcriptaccessrequestid'>>): Promise<IOperationResult<Pvci_transcriptaccessrequests>> {
    return Pvci_transcriptaccessrequestsService.client.updateRecordAsync<Partial<Omit<Pvci_transcriptaccessrequestsBase, 'pvci_transcriptaccessrequestid'>>, Pvci_transcriptaccessrequests>(
      Pvci_transcriptaccessrequestsService.dataSourceName,
      id,
      changedFields
    );
  }

  public static async get(id: string, options?: IGetOptions): Promise<IOperationResult<Pvci_transcriptaccessrequests>> {
    return Pvci_transcriptaccessrequestsService.client.retrieveRecordAsync<Pvci_transcriptaccessrequests>(
      Pvci_transcriptaccessrequestsService.dataSourceName,
      id,
      options
    );
  }

  public static async getAll(options?: IGetAllOptions): Promise<IOperationResult<Pvci_transcriptaccessrequests[]>> {
    return Pvci_transcriptaccessrequestsService.client.retrieveMultipleRecordsAsync<Pvci_transcriptaccessrequests>(
      Pvci_transcriptaccessrequestsService.dataSourceName,
      options
    );
  }

  public static getMetadata(options: GetEntityMetadataOptions<Pvci_transcriptaccessrequests> = {}): Promise<IOperationResult<Partial<EntityMetadata>>> {
    return Pvci_transcriptaccessrequestsService.client.executeAsync({
      dataverseRequest: {
        action: 'getEntityMetadata',
        parameters: {
          tableName: Pvci_transcriptaccessrequestsService.dataSourceName,
          options: options as GetEntityMetadataOptions,
        },
      },
    });
  }
}