# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

from pydantic import BaseModel

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
- `all_previous_steps_completed` should be `false` (no agents have run yet)
- `current_step` should be Step 1
- `inputs` should be empty (no prior outputs exist)

---

# KEY PRINCIPLES

1. **Follow the plan**: Stick to the original plan steps unless there's a solid reason to deviate
2. **Sequential steps**: Complete one task before moving to next
3. **Reference by ID**: Use response_ids for previous outputs - ONLY if they actually exist in conversation
4. **Natural language**: Write instructions as you would to a teammate
5. **Track context**: Always include user intent, plan + what's been done
6. **Minimal details**: No file paths, coordinates, or technical specs - agents know their job
7. **Input Validation**: Verify required inputs for the next step are available IN ACTUAL AGENT RESPONSES
8. **Output Validation**: Check that the last response matches expected type/content
9. **Action Decision**: If anything is missing or incorrect, fetch, clarify, or correct before proceeding

---

# Instruction Notes:
- Raster Ops Agent: Do not spcify the type of indicies or 


---

Please output an answer in pure JSON format according to the following schema. The JSON object must be parsable as-is. DO NOT OUTPUT ANYTHING OTHER THAN JSON, AND DO NOT DEVIATE FROM THIS SCHEMA:

{{
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
            "available": array of strings (list what data we currently have FROM ACTUAL AGENT RESPONSES),
            "missing_inputs_for_next_agent": array of strings (list what's missing, empty if none),
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
        "answer": {{
        "instruction": "string",
        "context": "string (2-4 lines: disaster type/dates/location, temporal windows with 
                   specific date ranges from plan, analysis type, required datasets, 
                   user intent and spatial scope)",
        "inputs": array of strings (list of response_ids ONLY from actual agent responses - empty list if first step or no prior outputs),
        "output_requirements": "string"
        }}
    }}

}}


# CRITICAL REMINDERS
- ✅ Use response_ids ONLY from actual agent responses in conversation history
- ✅ If no agents have responded yet, inputs MUST be an empty list []
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
- ❌ Don't hallucinate response_ids - if no agent has responded, inputs = []
"""
