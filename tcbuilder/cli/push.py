"""Push sub-command CLI handling

The push sub-command makes use of aktualizr's SOTA tools (specifically
garage-push and garage-sign) to sign & push a new OSTree to be deployed over OTA
to the devices.
"""

import os
import logging
import traceback
from tcbuilder.backend import push
from tcbuilder.errors import TorizonCoreBuilderError


def push_subcommand(args):
    """Run \"push\" subcommand"""
    log = logging.getLogger("torizon." + __name__)

    storage_dir = os.path.abspath(args.storage_directory)
    credentials = os.path.abspath(args.credentials)

    if args.ostree is not None:
        src_ostree_archive_dir = os.path.abspath(args.ostree)
    else:
        src_ostree_archive_dir = os.path.join(storage_dir, "ostree-archive")

    tuf_repo = os.path.join("/deploy", "tuf-repo")

    if not os.path.exists(storage_dir):
        log.error(f"{storage_dir} does not exist")
        return

    try:
        print(args.hardwareids)
        hardwareids = ",".join(args.hardwareids)
        push.push_ref(src_ostree_archive_dir, tuf_repo, credentials, args.ref, hardwareids)
    except TorizonCoreBuilderError as ex:
        log.error(ex.msg)  # msg from all kinds of Exceptions
        if ex.det is not None:
            log.info(ex.det)  # more elaborative message
        log.debug(traceback.format_exc())  # full traceback to be shown for debugging only

def init_parser(subparsers):
    """Initialize argument parser"""
    subparser = subparsers.add_parser("push", help="""\
    Push branch to OTA server""")
    subparser.add_argument("--credentials", dest="credentials",
                           help="""Relative path to credentials.zip.""",
                           required=True)
    subparser.add_argument("--repo", dest="ostree",
                           help="""OSTree repository to push from.""",
                           required=False)
    subparser.add_argument("--hardwareid", dest="hardwareids", action='append',
                           help="""Hardware IDs to use when creating and signing targets.json.""",
                           required=False, default=None)
    subparser.add_argument(metavar="REF", nargs="?", dest="ref",
                           help="""OSTree reference to deploy.""")

    subparser.set_defaults(func=push_subcommand)
