import logging
import os
import shutil
import gi
gi.require_version('OSTree', '1.0')
from gi.repository import GLib, Gio, OSTree
from tcbuilder.backend.common import TorizonCoreBuilderError
from tcbuilder.backend import ostree

log = logging.getLogger("torizon." + __name__)

def commit_changes(repo, diff_dir, branch_name):
    # ostree --repo=toradex-os-tree commit -b my-changes --tree=dir=my-changes
    log.debug("Committing changes from %s to %s", diff_dir, branch_name)
    if not repo.prepare_transaction():
        raise TorizonCoreBuilderError("Error preparing transaction.")

    mt = OSTree.MutableTree.new()
    changesdir_fd = os.open(diff_dir, os.O_DIRECTORY)

    if not repo.write_dfd_to_mtree(changesdir_fd, ".", mt):
        raise TorizonCoreBuilderError("Error adding directory to ostree commit")

    result, root = repo.write_mtree(mt)
    if not result:
        raise TorizonCoreBuilderError("Write mtree failed.")

    result, commit = repo.write_commit(None, None, None, None, root)
    if not result:
        raise TorizonCoreBuilderError("Write commit failed.")

    repo.transaction_set_ref(None, branch_name, commit)
    result, stats = repo.commit_transaction()
    if not result:
        raise TorizonCoreBuilderError("Commit failed.")

    log.debug("Transaction committed. %s bytes %s objects written.", str(
        stats.content_bytes_written), str(stats.content_objects_written))

    return commit


def merge_branch(repo, base_ref, diff_branch, tmp_checkout_rootfs_dir):
    OSTREE_GIO_FAST_QUERYINFO = ("standard::name,standard::type,standard::size,standard::is-symlink,standard::symlink-target,"
                                 "unix::device,unix::inode,unix::mode,unix::uid,unix::gid,unix::rdev")

    # ostree --repo=toradex-os-tree checkout -U --union torizon/torizon-core-docker temporary-rootfs

    # get commit from base ref name
    result, base_commit = repo.resolve_rev(base_ref, False)
    log.debug("Merging base reference %s (commit %s)...",
                  base_ref, base_commit)
    if not result:
        raise TorizonCoreBuilderError("Error getting remote commit.")

    # checkout to temp directory
    log.debug("Checking out tree to %s...", tmp_checkout_rootfs_dir)
    options = OSTree.RepoCheckoutAtOptions()
    options.overwrite_mode = OSTree.RepoCheckoutOverwriteMode.UNION_FILES
    options.process_whiteouts = False
    options.mode = OSTree.RepoCheckoutMode.NONE
    tmp_fd = os.open(tmp_checkout_rootfs_dir, os.O_DIRECTORY)
    if not repo.checkout_at(options,
                            tmp_fd,
                            ".", base_commit, None):
        raise TorizonCoreBuilderError("Error checking out remote tree.")

    # get commit from changes branch name
    result, diff_commit = repo.resolve_rev(diff_branch, False)
    log.debug("Merging local %s - commit %s...", diff_branch, diff_commit)
    if not result:
        raise TorizonCoreBuilderError("Error getting local commit.")

    log.debug("Merging into %s...", tmp_checkout_rootfs_dir)
    options.process_whiteouts = True
    if not repo.checkout_at(options,
                            tmp_fd,
                            ".", diff_commit, None):
        raise TorizonCoreBuilderError("Error checking out local tree.")


def union_changes(storage_dir, diff_dir, sysroot_dir, ostree_archive_dir, union_branch):
    try:
        sysroot = ostree.load_sysroot(sysroot_dir)
        deployment = sysroot.get_deployments()[0]
        base_csum = deployment.get_csum()
        repo = ostree.open_ostree(ostree_archive_dir)

        # create commit of changes
        diff_branch = "isolated_changes"
        commit_changes(repo, diff_dir, diff_branch)

        ''' create temporary checked-out rootfs from unpacked repo to merge 
        commit from changes directory. Changes cannot be directly written to
        ostree deployed branch. temporary checked-out rootfs is needed to be 
        created and commit is needed to be merged in it. We can not simply copy
        files to even checked-out temporary rootfs.
        '''
        tmp_checkout_rootfs_dir = os.path.join(storage_dir, "tmp_chkout_rootfs")

        if os.path.exists(tmp_checkout_rootfs_dir):
            shutil.rmtree(tmp_checkout_rootfs_dir)

        os.makedirs(tmp_checkout_rootfs_dir)
        merge_branch(repo, base_csum, diff_branch, tmp_checkout_rootfs_dir)
        # commits merged version
        final_commit = commit_changes(repo, tmp_checkout_rootfs_dir, union_branch)

        if os.path.exists(tmp_checkout_rootfs_dir):
            shutil.rmtree(tmp_checkout_rootfs_dir)

        sysroot.unload()
        return final_commit
    except Exception as ex:
        raise TorizonCoreBuilderError("issue occurred during creating a commit for changes. Contact Developer") \
             from ex
