import logging

import azure.functions as func

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

app = func.FunctionApp()
