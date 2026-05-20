# Behavior Synthesis error code.

int16 value

# Error code constants.

# Overall result.
int16 UNKNOWN = 0
int16 SUCCESS = 1
int16 FAILURE = -9999  # Last-resort generic failure; prefer a specific code below.

# Synthesis management errors.
# Reserved range: -1 through -9.
int16 BEHAVIOR_SYNTHESIS_FAILED = -1
int16 INVALID_REQUEST = -2
int16 PIPELINE_INVALID = -3
int16 MAPPING_INVALID = -4
int16 USERDATA_INVALID = -5
int16 PREEMPTED = -9
# ...

# Specification compilation errors.
# Reserved range: -10 through -19.
int16 SPEC_COMPILATION_FAILED = -10
int16 INVALID_COMPILER = -11  # The compiler parameter is not a valid entry_point.
# ...

# Synthesis errors.
# Reserved range: -20 through -29.
int16 SYNTHESIS_FAILED = -20
int16 SPEC_UNSYNTHESIZABLE = -21
int16 INVALID_SYNTHESIZER = -22  # The synthesizer parameter is not a valid entry_point.
# ...

# State machine generation errors.
# Reserved range: -30 through -49.
int16 SM_GENERATION_FAILED = -30  # State machine generation failed.
int16 NO_SYSTEMS_FILE = -31  # There is no system.yaml file.
int16 NO_SYSTEM_CONFIG = -32  # This system is not in system.yaml.
int16 SYSTEM_CONFIG_NOT_FOUND = -33  # This system is in system.yaml but was not found.
int16 CONFIG_FILE_INVALID = -34  # The config file is invalid.
int16 CONFIG_AUTONOMY_INVALID = -35  # The config autonomy is invalid.
int16 CONFIG_VARIABLE_CONFIG_INVALID = -36  # The variable config is invalid.
int16 AUTOMATON_INVALID = -37  # The automaton is invalid.
int16 AUTOMATON_NO_INITIAL_STATE = -38  # Unable to deduce the initial state.
int16 AUTOMATON_NEXT_STATE_INVALID = -39  # The next state does not map to anything.
int16 AUTOMATON_INPUT_VALUATION_INVALID = -40  # The input valuations are invalid.
int16 AUTOMATON_OUTPUT_VALUATION_INVALID = -41  # The output valuations are invalid.
int16 CONFIG_USERDATA_INVALID = -42  # The config userdata is invalid.
int16 INVALID_SM_GENERATOR = -43  # The SM generator parameter is not a valid entry_point.
