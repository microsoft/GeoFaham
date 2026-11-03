# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

from pydantic import BaseModel
from typing import Literal

class LedgerEntryBooleanAnswer(BaseModel):
    reason: str
    answer: bool


class LedgerEntryStringAnswer(BaseModel):
    reason: str
    answer: str


class PlanAdherenceCheck(BaseModel):
    current_step: str
    all_previous_steps_completed: bool
    required_artifacts_present: bool
    can_skip_step: bool
    skip_reason: str


class InputValidationCheck(BaseModel):
    next_agent_needs: list[str]
    available_in_ledger: list[str]
    missing_inputs: list[str]
    data_type_matches: bool
    can_proceed: bool


class OutputValidationCheck(BaseModel):
    last_agent_response_summary: str
    expected_output: str
    output_matches_expectation: bool
    output_is_usable_for_next_step: bool


class ValidationChecks(BaseModel):
    plan_adherence: PlanAdherenceCheck
    input_validation: InputValidationCheck
    output_validation: OutputValidationCheck


class InstructionOrQuestion(BaseModel):
    reason: str
    instruction: str
    context: str
    inputs: list[str]
    output_requirements: str


class LedgerEntry(BaseModel):
    stop_reason: str = ""
    temporal_mode: Literal["unspecified", "single_scene", "composite", "change_detection"]
    validation_checks: ValidationChecks
    is_request_satisfied: LedgerEntryBooleanAnswer
    is_in_loop: LedgerEntryBooleanAnswer
    is_progress_being_made: LedgerEntryBooleanAnswer
    next_speaker: LedgerEntryStringAnswer
    instruction_or_question: InstructionOrQuestion


ORCHESTRATOR_PROGRESS_LEDGER_PROMPT = """
Recall we are working on the following request:

{task}

And we have assembled the following team:

{team}

---

{agent_capabilities}

---
# YOUR ROLE

To make progress on the request, please answer the following questions, including necessary reasoning:

    - Is the request fully satisfied? (True if complete, or False if the original request has yet to be SUCCESSFULLY and FULLY addressed)
    - Are we in a loop where we are repeating the same requests and / or getting the same responses as before? Loops can span multiple turns, and can include repeated actions like scrolling up or down more than a handful of times.
    - Are we making forward progress? (True if just starting, or recent messages are adding value. False if recent messages show evidence of being stuck in a loop or if there is evidence of significant barriers to success such as the inability to read from a required file)
    - Who should speak next? (select from: {names}) - **MUST pass all 3 validation checks above before selecting**
    - What instruction or question would you give this team member? This should include: 
        - One line of instruction/question
        - Two to four lines of context including disaster details (type, dates, location), 
          temporal windows (pre-event, during-event, post-event date ranges from the plan), 
          analysis type (extent mapping, damage assessment, recovery monitoring), 
          required datasets/outputs specified in the plan step, and user intent.
        - One line of output requirements (according to plan)
        - What inputs/references does the next agent need? (List response_ids values references they should use)

---

# CRITICAL: DISTINGUISHING PLAN FROM EXECUTION

**The plan describes EXPECTED outputs - these are NOT actual outputs until an agent executes and returns them.**

Before claiming any step is complete, you MUST verify:
1. An agent message exists in the conversation history for that step
2. The agent's response contains actual data/artifacts (not just the plan's expectations)
3. A valid `response_id` exists that can be referenced

**Common hallucination to avoid:**
- The plan says "Expected Output: disaster_aoi.geojson" → This is a PLAN, not an actual file
- Only after postgis_agent/map_search_agent actually runs and returns a response with a `response_id` does that output exist

**If this is the first turn after planning:**
    - `all_previous_steps_completed` should be `true` for Step 1 (there are no earlier plan steps)
- `current_step` should be Step 1
- `inputs` must include any registered user uploads, drawn AOIs or existing responses needed by Step 1. Use [] only when the step needs no registered inputs.

---

# KEY PRINCIPLES

1. **Follow the plan**: Stick to the original plan steps unless there's a solid reason to deviate
2. **Sequential steps**: Complete one task before moving to next
3. **Reference by ID**: Use response_ids only from actual registered responses, including user uploads and drawn AOIs
4. **Natural language**: Write instructions as you would to a teammate
5. **Track context**: Always include user intent, plan + what's been done
6. **Minimal details**: No file paths, coordinates, or technical specs - agents know their job
7. **Input Validation**: Verify required inputs are available in actual registered user or agent responses
8. **Output Validation**: Check that the last response matches expected type/content
9. **Action Decision**: If anything is missing or incorrect, fetch, clarify, or correct before proceeding

---

# VALIDATION AND TEMPORAL REQUIREMENTS
- Set stop_reason to an empty string to continue or finish successfully. If an actual
  tool error prevents the requested work and there is no useful recovery within the
  user's constraints, set stop_reason to a concise explanation, keep
  is_request_satisfied.answer=false, and reference the failed response ID(s) in inputs.
  This ends with an incomplete-work answer, without dispatching another agent or
  requiring failed dependencies to pass validation. Error responses may support
  stopping, never a successful computation or completion claim. Do not retry an
  unavailable service merely to make an unsuccessful workflow appear complete.
- Set temporal_mode to single_scene for a single-date imagery analysis, composite only
  when temporal aggregation is requested, change_detection for pre/post comparisons,
  otherwise unspecified. Keep it unchanged throughout this request.
- Include "Temporal mode: <temporal_mode>" in raster instructions and require that
  execute_custom_raster_code receives that exact temporal_mode argument.
- For single_scene, select one acquisition date before loading imagery. Several candidate
  scenes do not authorize a composite. Require scene IDs and acquisition dates in outputs.
- Set can_proceed only when required inputs are available; an empty missing_inputs list
  describes prerequisites, not the computation the next agent is about to perform.
- When a step has no artifact prerequisites, required_artifacts_present is true.
- Use [] for missing_inputs when none are missing, never ["None"].
- If no prior output is expected, output_matches_expectation/output_is_usable_for_next_step
  may be false. When declaring completion, they and the plan/input checks must be true.
- A completed task must reference its final evidence in instruction_or_question.inputs.
- Failed code checks are execution evidence: correct the failed step or report incomplete
  work. Do not claim a layer exists based on a summary when its artifact path is invalid.


---

Please output an answer in pure JSON format according to the following schema. The JSON object must be parsable as-is. DO NOT OUTPUT ANYTHING OTHER THAN JSON, AND DO NOT DEVIATE FROM THIS SCHEMA:

{{
    "stop_reason": string (empty to continue/succeed; otherwise explain why actual tool failure prevents completion),
    "temporal_mode": string (unspecified, single_scene, composite, or change_detection; preserve the user request),
    "validation_checks": {{
        "plan_adherence": {{
            "current_step": string (e.g., "Step 2: Fetch hospital POIs"),
            "all_previous_steps_completed": boolean,
            "required_artifacts_present": boolean,
            "can_skip_step": boolean,
            "skip_reason": string (if can_skip_step is true, explain why; otherwise empty string)
        }},
        "input_validation": {{
            "next_agent_needs": array of strings (list what the next agent needs),
            "available_in_ledger": array of strings (list actual registered user or agent responses),
            "missing_inputs": array of strings (list what's missing, empty if none),
            "data_type_matches": boolean,
            "can_proceed": boolean
        }},
        "output_validation": {{
            "last_agent_response_summary": string (what did the last agent return? Say "No agent has responded yet" if first turn),
            "expected_output": string (what did we expect?),
            "output_matches_expectation": boolean,
            "output_is_usable_for_next_step": boolean
        }}
    }},
    "is_request_satisfied": {{
        "reason": string,
        "answer": boolean
    }},
    "is_in_loop": {{
        "reason": string,
        "answer": boolean
    }},
    "is_progress_being_made": {{
        "reason": string,
        "answer": boolean
    }},
    "next_speaker": {{
        "reason": string (explain why this agent was selected after passing validation checks),
        "answer": string (select from: {names})
    }},
    "instruction_or_question": {{
        "reason": "string",
        "instruction": "string",
        "context": "string (2-4 lines: disaster type/dates/location, temporal windows with 
                   specific date ranges from plan, analysis type, required datasets, 
                   user intent and spatial scope)",
        "inputs": array of strings (response_ids from actual registered user or agent responses needed by this step; empty only when none are needed),
        "output_requirements": "string"
    }}

}}


# CRITICAL REMINDERS
- ✅ Use response_ids only from actual registered user or agent responses in context
- ✅ User uploads and drawn AOIs can be valid inputs before any agent has responded
- ✅ Keep instructions minimal and natural language
- ✅ Include user context in every instruction
- ✅ Follow the plan sequentially
- ✅ Validate that required artifacts exist IN ACTUAL RESPONSES before proceeding
- ✅ One task per agent per turn
- ✅ Always check agent capabilities
- ❌ Don't confuse plan's "Expected Output" with actual outputs
- ❌ Don't micromanage with technical details
- ❌ Don't use vague references like "from Step 1"
- ❌ Don't skip steps or combine multiple tasks
- ❌ Don't do parallel call
- ❌ Don't write anything else in "inputs" other than response_ids values references if you need to write any (wrong: ["response_id:response_8a2b3373-92a"] correct: ["response_8a2b3373-92a"]). If some extra information is to be sent to the next agent, use instruction or context.
- ❌ Don't hallucinate response_ids; a planned output is never a registered input
"""
