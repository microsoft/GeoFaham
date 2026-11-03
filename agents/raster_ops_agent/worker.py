"""Run generated raster work in a process that can be stopped."""
import asyncio
import multiprocessing

from agents.core.config import ConfigProvider, get_config
from agents.core.constants import AGENT_NAMES
from agents.raster_ops_agent.sandbox import strip_secrets
from agents.shared.responses import build_error_response


def _run_raster(send, arguments, config):
    try:
        with ConfigProvider.override(config):
            from agents.raster_ops_agent import io_utils
            from agents.raster_ops_agent.tools import _execute_custom_raster_code
            from agents.raster_ops_agent.sandbox import install_io_guard, scrub_environment
            io_utils.QUERY_JSONS_PATH = str(config.paths.export_dir)
            scrub_environment()
            install_io_guard(config.paths.base_dir, config.paths.data_dir)
            send.send(asyncio.run(_execute_custom_raster_code(**arguments)))
    except Exception as error:
        send.send(build_error_response(source=AGENT_NAMES["RASTER_AGENT"],
                                       error_message=f"Raster worker failed: {error}"))
    finally:
        send.close()


async def execute_raster_in_process(arguments):
    config = strip_secrets(get_config())
    timeout = config.query.raster_timeout_seconds
    context = multiprocessing.get_context("spawn")
    receive, send = context.Pipe(duplex=False)
    process = context.Process(target=_run_raster, args=(send, arguments, config))
    try:
        process.start()
        send.close()
        return await asyncio.wait_for(asyncio.to_thread(receive.recv), timeout=timeout)
    except TimeoutError:
        return build_error_response(
            source=AGENT_NAMES["RASTER_AGENT"],
            error_message=f"Raster execution exceeded {timeout} seconds and was stopped",
            metadata={"execution_error": True, "error_type": "timeout"},
        )
    except EOFError:
        return build_error_response(source=AGENT_NAMES["RASTER_AGENT"],
                                    error_message="Raster execution process exited without a result")
    finally:
        if process.pid is not None:
            if process.is_alive():
                process.terminate()
            await asyncio.to_thread(process.join, 2)
            if process.is_alive():
                process.kill()
                await asyncio.to_thread(process.join)
            process.close()
        receive.close()
        send.close()
