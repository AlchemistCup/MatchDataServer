import logging

def addLoggingLevel(levelName, levelNum, methodName=None):
    """
    Comprehensively adds a new logging level to the `logging` module and the currently configured logging class. https://stackoverflow.com/a/35804945

    @param levelName: Name of new level
    @param levelNum: Value of new level
    @param methodName: Name of convenience function to log to the new level. Uses levelName.lower() by default.

    This method will raise an `AttributeError` if the level name is already an attribute of the `logging` module or if the method name is already present 
    """
    if not methodName:
        methodName = levelName.lower()

    if hasattr(logging, levelName):
       raise AttributeError('{} already defined in logging module'.format(levelName))
    if hasattr(logging, methodName):
       raise AttributeError('{} already defined in logging module'.format(methodName))
    if hasattr(logging.getLoggerClass(), methodName):
       raise AttributeError('{} already defined in logger class'.format(methodName))

    def logForLevel(self, message, *args, **kwargs):
        if self.isEnabledFor(levelNum):
            self._log(levelNum, message, args, **kwargs)
    def logToRoot(message, *args, **kwargs):
        logging.log(levelNum, message, *args, **kwargs)

    logging.addLevelName(levelNum, levelName)
    setattr(logging, levelName, levelNum)
    setattr(logging.getLoggerClass(), methodName, logForLevel)
    setattr(logging, methodName, logToRoot)

addLoggingLevel('DEBUG2', logging.DEBUG - 1)

loggers = {}

def get_logger(name) -> logging.Logger:
    global loggers

    if loggers.get(name):
        return loggers.get(name)
    
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG)

    fh = logging.FileHandler('test.log')
    fh.setLevel(logging.INFO)

    formatter = logging.Formatter('%(asctime)s [%(levelname)-s] [%(name)-5s] %(message)s')
    ch.setFormatter(formatter)
    fh.setFormatter(formatter)
    logger.addHandler(ch)
    logger.addHandler(fh)

    loggers[name] = logger
    return logger
