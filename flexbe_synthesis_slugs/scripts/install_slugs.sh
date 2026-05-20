# Installation script for slugs
# on Linux and Darwin (Mac OS X)
#
# FlexBE Synthesis uses the CNU Robotics fork and flexbe-synthesis branch for
# Python 3 compatibility changes and synthesis enhancements.
# Tested baseline: 844e680. The branch is expected to remain compatible.
#
# This script is an extension of the
# one written by https://github.com/johnyf
#

set -e

INSTALL=${SLUGS_INSTALL_DIR:-/usr/local/bin}
SLUGS_REPO=https://github.com/CNURobotics/slugs.git
SLUGS_BRANCH=flexbe-synthesis
TESTED_SLUGS_COMMIT=844e680

if ! command -v git >/dev/null 2>&1; then
	echo "  ERROR: git is required to clone ${SLUGS_REPO}."
	exit 1
fi

if ! command -v make >/dev/null 2>&1; then
	echo "  ERROR: make is required to build Slugs."
	exit 1
fi

if [ -x "${INSTALL}/slugs" ]; then
	echo "slugs is already installed in ${INSTALL}"
	exit 0
elif command -v slugs >/dev/null 2>&1; then
	echo "  slugs is already available in the path"
	echo $PATH
	exit 0
fi

echo "Need to install slugs in '${INSTALL}' ..."
echo "  Using ${SLUGS_REPO} (${SLUGS_BRANCH}); tested baseline ${TESTED_SLUGS_COMMIT}"

# fetch slugs
if ! [ -d "slugs" ] ; then
	echo "  Cloning ${SLUGS_REPO} (${SLUGS_BRANCH}) ..."
	if ! git clone --branch "${SLUGS_BRANCH}" --single-branch "${SLUGS_REPO}" slugs; then
		echo "  ERROR: failed to clone ${SLUGS_REPO} branch ${SLUGS_BRANCH}."
		echo "  Check network access and confirm the branch still exists."
		exit 1
	fi
else
	echo "  Using existing slugs checkout; expected ${SLUGS_REPO} branch ${SLUGS_BRANCH}"
fi
cd slugs/
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
	CURRENT_BRANCH=$(git branch --show-current 2>/dev/null || true)
	if [ -n "${CURRENT_BRANCH}" ] && [ "${CURRENT_BRANCH}" != "${SLUGS_BRANCH}" ]; then
		echo "  WARNING: existing slugs checkout is on '${CURRENT_BRANCH}', expected '${SLUGS_BRANCH}'."
	fi
fi

# build slugs
echo "  Building the slugs library ..."
cd src/
if ! [ -e "slugs" ] ; then
	if ! make; then
		echo "  ERROR: failed to build Slugs."
		echo "  Install a compiler toolchain and required build dependencies, then rerun this script."
		exit 1
	fi
fi

echo "  Installing slugs to '${INSTALL}' ..."
if ! mkdir -p "${INSTALL}"; then
	echo "  ERROR: failed to create install directory '${INSTALL}'."
	echo "  Set SLUGS_INSTALL_DIR to a writable directory or create the path manually."
	exit 1
fi
if [ -w "${INSTALL}" ]; then
	if ! cp slugs "${INSTALL}/slugs"; then
		echo "  ERROR: failed to copy Slugs to '${INSTALL}/slugs'."
		exit 1
	fi
else
	if ! command -v sudo >/dev/null 2>&1; then
		echo "  ERROR: '${INSTALL}' is not writable and sudo is not available."
		echo "  Set SLUGS_INSTALL_DIR to a writable directory, such as '${HOME}/.local/bin'."
		exit 1
	fi
	if ! sudo cp slugs "${INSTALL}/slugs"; then
		echo "  ERROR: failed to copy Slugs to '${INSTALL}/slugs' with sudo."
		echo "  Set SLUGS_INSTALL_DIR to a writable directory to install without sudo."
		exit 1
	fi
fi
echo $PATH

# check success
if [ -x "${INSTALL}/slugs" ]; then
	echo "  Successfully installed slugs in ${INSTALL}"
	if ! command -v slugs >/dev/null 2>&1; then
		echo "  WARNING: '${INSTALL}' is not currently on PATH."
		echo "  Add it to PATH before running FlexBE Synthesis."
	fi
else
	echo "  ERROR: slugs failed to install to '${INSTALL}/slugs'."
	exit 1
fi

# clean up afterwards
echo "Clean up slugs repo ..."
cd ../../ && rm -rf slugs
echo "Done!"
