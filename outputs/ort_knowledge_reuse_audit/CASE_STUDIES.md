# ORT source examples

Actual expanded section text from the audited files. This text view flattens lists and tables; use the linked DITA source to inspect their structure. These examples illustrate the method; they are not an unbiased precision sample.


## Access code: FTS versus Cúram

Shared security wording does not erase the system and indicator differences. Review the common statements separately from the system-specific sentence.

### Detailed security check

[Open original DITA source](D:/Deduplication_Agent/unzipped/ort_new_dita/dita/en_EN/activity/access_code/detailed_security_check.dita)

`en_EN/activity/access_code/detailed_security_check.dita`

**Expanded body:**

A detailed security check must be conducted with the client before providing information or issuing an access code. The agent does not accept requests to reissue an access code from a third party, unless it is from the designated representative. In the case of a representative, ensure that there is no electronic document indicating that the client has recovered and no longer requires the services of the representative. Representatives are identified in FTS with the indicator “/REP/”. For additional information, refer to Appointment of representative — Limited physical or mental capacity . Appointment of representative — Limited physical or mental capacity

### Detailed security check

[Open original DITA source](D:/Deduplication_Agent/unzipped/ort_new_dita/dita/en_EN/task/envoyer-code-acces-issue-access-code-curam/detailed_security_check.dita)

`en_EN/task/envoyer-code-acces-issue-access-code-curam/detailed_security_check.dita`

**Expanded body:**

A detailed security check must be conducted with the client before providing information or issuing an access code. The officer does not accept requests to reissue an access code from a third party, unless it is from the designated representative. In the case of a representative, ensure that there is no electronic document indicating that the client has recovered and no longer requires the services of the representative. Representatives are identified in Cúram with the indicator “REP”. For additional information, refer to Appointment of representative — Limited physical or mental capacity . Appointment of representative — Limited physical or mental capacity

### Detailed security check

[Open original DITA source](D:/Deduplication_Agent/unzipped/ort_new_dita/dita/en_EN/task/replacing_ac/detailed_security_check.dita)

`en_EN/task/replacing_ac/detailed_security_check.dita`

**Expanded body:**

A detailed security check must be conducted with the client before providing information or issuing an access code. The officer does not accept requests to reissue an access code from a third party, unless it is from the designated representative. In the case of a representative, ensure that there is no electronic document indicating that the client has recovered and no longer requires the services of the representative. Representatives are identified in FTS with the indicator “REP”. For additional information, refer to Appointment of representative — Limited physical or mental capacity . Appointment of representative — Limited physical or mental capacity

## RFS summary: Quit versus Dismissal

Preserve E–Quit and M–Dismissal as applicability conditions. These are variants, not interchangeable instructions.

### Summary

[Open original DITA source](D:/Deduplication_Agent/unzipped/ort_new_dita/dita/en_EN/task/roe_quit/summary.dita)

`en_EN/task/roe_quit/summary.dita`

**Expanded body:**

Summary: When an ROE is received with a reason for separation (RFS) E - Quit on an initial Web application, if the system is unable to create a link between the ROE and a matching period of employment or determine if the issue requires adjudication, an ROE Issue (ROE) RFS Action WI is created.

### Summary

[Open original DITA source](D:/Deduplication_Agent/unzipped/ort_new_dita/dita/en_EN/task/roe_dismissal/summary.dita)

`en_EN/task/roe_dismissal/summary.dita`

**Expanded body:**

Summary: When an ROE is received with a reason for separation (RFS) M - Dismissal on an initial Web application, if the system is unable to create a link between the ROE and a matching period of employment or determine if the issue requires adjudication, an ROE Issue (ROE) RFS Action WI is created.

## RFS linking: hidden table differences

Raw normalized bodies matched, but expanding conrefs reveals different E/M table values. Six existing internal elements match exactly. A table example difference alone does not prove contradictory policy.

### Linking the ROE and the matching period of employment

[Open original DITA source](D:/Deduplication_Agent/unzipped/ort_new_dita/dita/en_EN/task/roe_quit/linking_the_roe_and_the_matching_period_f71580ff.dita)

`en_EN/task/roe_quit/linking_the_roe_and_the_matching_period_f71580ff.dita`

**Expanded body:**

When an ROE RFS Action WI is received and a link has not yet been created between the ROE and a period of employment, the Non-complex agent must review the applicable ROE in RCM and the periods of employment listed in NWS. The Non-complex agent determines if one of the periods of employment listed in NWS matches the employer’s name on the ROE. Variations in the employer’s name Minor spelling differences between the employer’s name on the ROE and the period of employment are accepted. The agent must also consider that the employer may do business under more than one name. For example, the ROE indicates that the employer’s name is 123456 ONT Inc., but the client reported working for ABC Company. If the documentation on file or the Employer search (by business number) in FTS indicates that 123456 ONT Inc. operates as ABC Company, the names are equivalent and considered to be a match. Reviewing the dates on the ROE Only one ROE can be matched to each period of employment listed in NWS. The agent must review the Search / Correct - Results screen in RCM to determine if the ROE in the ROE RFS Action WI is the one with the last day for which paid (LDP) closest to the last day worked (LDW) for one of the periods of employment. The agent creates a link between the ROE and the period of employment with the matching employer’s name and best match for LDP and LDW. If either the employer’s name does not match or the LDP and LDW are not a good match, the agent does not create a link between the ROE and the period of employment. More than one ROE for one period of employment There may be more than one ROE but only one period of employment for the same employer. Example 1 Period of employment information declared on application: Callout Search / Correct - Results in RCM: SN Employer FDW / TSD LDP / TED Modified Input RFS Audit EHF W12345678 ABC Company 01/07/2015 04/12/2015 22/12/2015 22/12/2015 E W12341234 ABC Company 01/01/2015 30/06/2015 22/12/2015 22/12/2015 K ROE RFS Action WI #1 for W12345678 The agent completes the period of employment information section as follows: Matching POE : Select ABC Company . ROE RFS Action WI #2 for W12341234 The agent completes the period of employment information section as follows: Matching POE : Select POE not in the list . There may also be more than one period of employment for the same employer. Example 2 Period of employment information declared on application: Callout Callout Search / Correct - Results in RCM: SN Employer FDW / TSD LDP / TED Modified Input RFS Audit EHF W12345678 ABC Company 01/07/2015 04/12/2015 22/12/2015 22/12/2015 E W12341234 ABC Company 01/01/2015 30/06/2015 22/12/2015 22/12/2015 K ROE RFS Action WI #1 for W12345678 The agent completes the period of employment information section as follows: Matching POE : Select ABC Company (LDW 30/11/2015). ROE RFS Action WI #2 for W12341234 The agent completes the period of employment information section as follows: Matching POE : Select ABC Company (LDW 30/07/2015). ROE already linked If the ROE is linked to a period of employment with a corresponding electronic record of decision (ROD) or an outstanding Adjudication Issue (ADJ) WI, the ROE RFS Action WI is completed without further action by the Non-complex agent.

### Linking the ROE and the matching period of employmen

[Open original DITA source](D:/Deduplication_Agent/unzipped/ort_new_dita/dita/en_EN/task/roe_dismissal/linking_the_roe_and_the_matching_period_e21c3afb.dita)

`en_EN/task/roe_dismissal/linking_the_roe_and_the_matching_period_e21c3afb.dita`

**Expanded body:**

When an ROE RFS Action WI is received and a link has not yet been created between the ROE and a period of employment, the Non-complex agent must review the applicable ROE in RCM and the periods of employment listed in NWS. The Non-complex agent determines if one of the periods of employment listed in NWS matches the employer’s name on the ROE. Variations in the employer’s name Minor spelling differences between the employer’s name on the ROE and the period of employment are accepted. The agent must also consider that the employer may do business under more than one name. For example, the ROE indicates that the employer’s name is 123456 ONT Inc., but the client reported working for ABC Company. If the documentation on file or the Employer search (by business number) in FTS indicates that 123456 ONT Inc. operates as ABC Company, the names are equivalent and considered to be a match. Reviewing the dates on the ROE Only one ROE can be matched to each period of employment listed in NWS. The agent must review the Search / Correct - Results screen in RCM to determine if the ROE in the ROE RFS Action WI is the one with the last day for which paid (LDP) closest to the last day worked (LDW) for one of the periods of employment. The agent creates a link between the ROE and the period of employment with the matching employer’s name and best match for LDP and LDW. If either the employer’s name does not match or the LDP and LDW are not a good match, the agent does not create a link between the ROE and the period of employment. More than one ROE for one period of employment There may be more than one ROE but only one period of employment for the same employer. Example 1 Period of employment information declared on application: Callout Search / Correct - Results in RCM: SN Employer FDW / TSD LDP / TED Modified Input RFS Audit EHF W12345678 ABC Company 01/07/2015 04/12/2015 22/12/2015 22/12/2015 M W12341234 ABC Company 01/01/2015 30/06/2015 22/12/2015 22/12/2015 K ROE RFS Action WI #1 for W12345678 The agent completes the period of employment information section as follows: Matching POE : Select ABC Company . ROE RFS Action WI #2 for W12341234 The agent completes the period of employment information section as follows: Matching POE : Select POE not in the list . There may also be more than one period of employment for the same employer. Example 2 Period of employment information declared on application: Callout Callout Search / Correct - Results in RCM: SN Employer FDW / TSD LDP / TED Modified Input RFS Audit EHF W12345678 ABC Company 01/07/2015 04/12/2015 22/12/2015 22/12/2015 M W12341234 ABC Company 01/01/2015 30/06/2015 22/12/2015 22/12/2015 K ROE RFS Action WI #1 for W12345678 The agent completes the period of employment information section as follows: Matching POE : Select ABC Company (LDW 30/11/2015). ROE RFS Action WI #2 for W12341234 The agent completes the period of employment information section as follows: Matching POE : Select ABC Company (LDW 30/07/2015). ROE already linked If the ROE is linked to a period of employment with a corresponding electronic record of decision (ROD) or an outstanding Adjudication Issue (ADJ) WI, the ROE RFS Action WI is completed without further action by the Non-complex agent.

## Genuine exact content across activity and task

Both expanded bodies are identical. Task/activity is context, not a reason to forbid comparison. Confirm applicability before proposing shared maintenance.

### Conditions for creating the WI

[Open original DITA source](D:/Deduplication_Agent/unzipped/ort_new_dita/dita/en_EN/activity/adj_rfs_review/conditions_for_creating_the_wi.dita)

`en_EN/activity/adj_rfs_review/conditions_for_creating_the_wi.dita`

**Expanded body:**

When none of the periods of employment reported on the application have a contentious RFS, or when all the periods of employment with a contentious RFS are already linked to an ROE, an ADJ RFS Review WI is created.

### Conditions for creating the WI

[Open original DITA source](D:/Deduplication_Agent/unzipped/ort_new_dita/dita/en_EN/task/adj_rfs_review_man_ret/conditions_for_creating_the_wi.dita)

`en_EN/task/adj_rfs_review_man_ret/conditions_for_creating_the_wi.dita`

**Expanded body:**

When none of the periods of employment reported on the application have a contentious RFS, or when all the periods of employment with a contentious RFS are already linked to an ROE, an ADJ RFS Review WI is created.
