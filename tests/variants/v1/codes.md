# Code list for close_call, transfer_to_agent and add_note

| Outcome | Reason | Used when |
|---|---|---|
| ptp | (none) | an arrangement was recorded |
| settled | (none) | the member says the overdue amount is already paid |
| handed_over | plans, agents, hardship_team | the call was transferred to that queue |
| no_ptp | declined, hardship, disputed, system_error | verified, no arrangement |
| unverified | failed, refused | the check failed, or the member would not answer |
| no_contact | callback, no_callback, wrong_number, deceased, unclear | the member was not reached |

Queues: plans (repayment plans), agents (a person), hardship_team (financial difficulty).

Notes (add_note) are not used for single-product members.
