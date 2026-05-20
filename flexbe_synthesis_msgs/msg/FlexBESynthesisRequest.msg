# A synthesis request consists of the system (i.e., a robot)
# for which to synthesize a behavior, the system's initial conditions,
# the desired objective(s) and the resulting state machine's outcomes.

# The system's initial condition(s) at start of the request
# Empty when the specification already provides all initial conditions.
string[] initial_conditions

# All request-level goals that must be achieved for a state machine's run to be
# successful. Empty when capabilities or additional specification files already
# encode the objective; in that case no request-derived goal constraints are
# added.
string[] goals

# The outcomes of the resulting synthesized state machine
# Empty for vanilla synthesized automata (infinite execution)
# By convention, 'finished' and 'failed' are used for success and failure.
# If non-empty, the first non-failure outcome is used as the request success
# outcome. If empty, request-driven synthesis defaults the success outcome to
# 'finished'.
string[] sm_outcomes

# The desired system for which to synthesize
# This name is used to locate the required files
string system_name

# All fields below are OPTIONAL
#------------------------------

# The compiled specification's name
# Useful for locating the generated files.
# Does not affect the server's response.
string spec_name

# Name of user-specified specifications file in specs folder
# under flexbe_synthesis hidden folder
string specification_file_name

# Maximum wall-clock time (seconds) the synthesis backend is allowed to run.
# 0.0 means use the pipeline's configured default.
float64 synthesis_timeout_s
