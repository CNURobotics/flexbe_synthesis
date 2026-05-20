cmake_minimum_required(VERSION 3.16)

project(flexbe_synthesis_msgs)

find_package(action_msgs REQUIRED)
find_package(ament_cmake REQUIRED)
find_package(flexbe_msgs REQUIRED)
find_package(rosidl_default_generators REQUIRED)

set(msg_files
    "msg/SynthesisErrorCode.msg"
    "msg/FlexBESynthesisRequest.msg"
)

set(action_files
    "action/FlexBESynthesis.action"
)

rosidl_generate_interfaces(${PROJECT_NAME}
    ${action_files}
    ${msg_files}
    ADD_LINTER_TESTS
    DEPENDENCIES action_msgs flexbe_msgs
    )

if(BUILD_TESTING)
  find_package(ament_cmake_pytest REQUIRED)
  ament_add_pytest_test(test_flake8 test/test_flake8.py)
  ament_add_pytest_test(test_pep257 test/test_pep257.py)
  ament_add_pytest_test(test_copyright test/test_copyright.py)
endif()

ament_export_dependencies(rosidl_default_runtime)

ament_package()
