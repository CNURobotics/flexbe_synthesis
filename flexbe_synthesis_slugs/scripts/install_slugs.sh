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
FORCE=0

usage() {
	echo "Usage: $0 [--force|-f]"
	echo "  -f, --force  Pull the latest Slugs source and rebuild even if it is installed."
}

while [ "$#" -gt 0 ]; do
	case "$1" in
		-f|--force)
			FORCE=1
			;;
		-h|--help)
			usage
			exit 0
			;;
		*)
			echo "  ERROR: unknown option '$1'."
			usage
			exit 2
			;;
	esac
	shift
done

if ! command -v git >/dev/null 2>&1; then
	echo "  ERROR: git is required to clone ${SLUGS_REPO}."
	exit 1
fi

if ! command -v make >/dev/null 2>&1; then
	echo "  ERROR: make is required to build Slugs."
	exit 1
fi

if [ "${FORCE}" -eq 0 ] && [ -x "${INSTALL}/slugs" ]; then
	echo "slugs is already installed in ${INSTALL}"
	exit 0
elif [ "${FORCE}" -eq 0 ] && command -v slugs >/dev/null 2>&1; then
	echo "  slugs is already available in the path"
	echo $PATH
	exit 0
fi

if [ "${FORCE}" -eq 1 ]; then
	echo "Forcing Slugs source update and rebuild ..."
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
	if [ "${FORCE}" -eq 1 ]; then
		echo "  Pulling latest ${SLUGS_BRANCH} source ..."
		if ! git checkout "${SLUGS_BRANCH}"; then
			echo "  ERROR: failed to switch the existing Slugs checkout to '${SLUGS_BRANCH}'."
			echo "  Resolve any local changes, then rerun this script."
			exit 1
		fi
		if ! git pull --ff-only origin "${SLUGS_BRANCH}"; then
			echo "  ERROR: failed to fast-forward the existing Slugs checkout."
			echo "  Resolve any local changes or branch divergence, then rerun this script."
			exit 1
		fi
	fi
elif [ "${FORCE}" -eq 1 ]; then
	echo "  ERROR: cannot update 'slugs' because it is not a Git checkout."
	exit 1
fi

# build slugs
echo "  Building the slugs library ..."
cd src/
if [ "${FORCE}" -eq 1 ]; then
	if ! make clean; then
		echo "  ERROR: failed to clean the existing Slugs build."
		exit 1
	fi
fi
if [ "${FORCE}" -eq 1 ] || ! [ -e "slugs" ] ; then
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
