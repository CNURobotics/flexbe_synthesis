# flexbe_synthesis_msgs

ROS 2 interface package for FlexBE behavior synthesis.

## Provided Interfaces

Messages:
- `msg/FlexBESynthesisRequest.msg`
- `msg/SynthesisErrorCode.msg`

Actions:
- `action/FlexBESynthesis.action`

## Interface Notes

`FlexBESynthesisRequest`
- `initial_conditions`: initial state predicates; may be empty when the loaded
  specification already provides the required initial conditions.
- `goals`: request-level goal predicates. This may be empty when capabilities
  or additional specification files already encode the objective.
- `sm_outcomes`: state machine outcomes (often `finished` and `failed`).
- `system_name`: logical system identifier used to locate synthesis configs.
- `spec_name`: optional generated spec label.
- `specification_file_name`: optional user spec file under `synthesis_home` (`~/.flexbe_synthesis` by default).
- `synthesis_timeout_s`: optional per-request timeout override (seconds). `0.0` (default) uses the pipeline-configured value.

`SynthesisErrorCode`
- `value` is the active code.
- `SUCCESS` indicates synthesis completed.
- Negative constants indicate different failure classes (compilation, synthesis,
  or state-machine generation).

`FlexBESynthesis.action`
- Goal:
  - `request`: `FlexBESynthesisRequest`.
  - `synthesis_options`: YAML dictionary serialized as string.
- Result:
  - `error_code`: `SynthesisErrorCode`.
  - `states`: `flexbe_msgs/StateInstantiation[]` synthesized state machine.
  - `messages`: `string[]`
- Feedback:
  - `status`: textual stage indicator.
  - `progress`: normalized `[0.0, 1.0]` progress value.

FlexBE WebUI v4.1.5+ works with this action interface.
