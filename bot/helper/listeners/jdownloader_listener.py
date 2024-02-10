from asyncio import sleep, wait_for

from bot import Intervals, jd_lock, jd_downloads, LOGGER
from bot.helper.ext_utils.bot_utils import new_task, sync_to_async, retry_function
from bot.helper.ext_utils.jdownloader_booter import jdownloader
from bot.helper.ext_utils.status_utils import getTaskByGid


@new_task
async def _onDownloadComplete(gid):
    task = await getTaskByGid(f"{gid}")
    if not task:
        return
    if task.listener.select:
        await retry_function(
            jdownloader.device.downloads.cleanup,
            "DELETE_DISABLED",
            "REMOVE_LINKS_AND_DELETE_FILES",
            "SELECTED",
            package_ids=jd_downloads[gid]["ids"],
        )
    await task.listener.onDownloadComplete()
    if Intervals["stopAll"]:
        return
    await retry_function(
        jdownloader.device.downloads.remove_links,
        package_ids=jd_downloads[gid]["ids"],
    )
    del jd_downloads[gid]


@new_task
async def _jd_listener():
    while True:
        await sleep(3)
        async with jd_lock:
            if len(jd_downloads) == 0:
                Intervals["jd"] = ""
                break
            try:
                await wait_for(retry_function(jdownloader.device.jd.version), timeout=5)
            except:
                is_connected = await sync_to_async(jdownloader.jdconnect)
                if not is_connected:
                    LOGGER.error(jdownloader.error)
                    continue
                await sync_to_async(jdownloader.connectToDevice)
            try:
                packages = await sync_to_async(
                    jdownloader.device.downloads.query_packages, [{"finished": True}]
                )
            except:
                continue
            finished = [
                pack["uuid"] for pack in packages if pack.get("finished", False)
            ]
            for gid in finished:
                if gid in jd_downloads and jd_downloads[gid]["status"] != "done":
                    is_finished = all(
                        did in finished for did in jd_downloads[gid]["ids"]
                    )
                    if is_finished:
                        jd_downloads[gid]["status"] = "done"
                        _onDownloadComplete(gid)


async def onDownloadStart():
    async with jd_lock:
        if not Intervals["jd"]:
            Intervals["jd"] = _jd_listener()