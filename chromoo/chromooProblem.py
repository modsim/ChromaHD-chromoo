from pymoo.core.problem import Problem
from itertools import chain
# from functools import partial
from multiprocessing import Pool

import copy
import string
import random

from chromoo.utils import keystring_todict, deep_get, sse, readChromatogram, readArray

import numpy as np
from pathlib import Path
import subprocess

class ChromooProblem(Problem):
    def __init__(self, sim, parameters, objectives, nproc=4, tempdir='temp'):
        
        xls = []
        xus = []

        # NOTE: Scalars are autoconverted to lists and chained
        for p in parameters:
            if isinstance(p.min_value, float):
                p.min_value = [p.min_value] * p.length
            if isinstance(p.max_value, float):
                p.max_value = [p.max_value] * p.length

            xls = list(chain(xls, p.min_value))
            xus = list(chain(xus, p.max_value))

        super().__init__(
            n_var = sum(p.get('length') for p in parameters), 
            n_obj = len(objectives), 
            n_constr=0, 
            # xl=[p.get('min_value') for p in parameters],
            # xu=[p.get('max_value') for p in parameters] )  
            xl=xls,
            xu=xus )

        self.sim = sim
        self.parameters = parameters
        self.objectives = objectives
        self.nproc = nproc

        self.tempdir=Path(tempdir)
        self.tempdir.mkdir(exist_ok=True)

    def _evaluate(self, x, out, *args, **kwargs):

        with Pool(self.nproc) as pool:
            out["F"] = pool.map(self.evaluate_sim, x)

    def evaluate_sim(self, x):
        """
            - run one simulation
            - calculate and return scores
        """
        newsim = copy.deepcopy(self.sim)
        newsim.filename = self.tempdir.joinpath('temp' + ''.join(random.choices(string.ascii_uppercase + string.ascii_lowercase + string.digits, k=6)) + '.h5')

        self.update_sim_parameters(newsim, x)

        newsim.save()

        try:
            newsim.run(check=True)
        except subprocess.CalledProcessError as error:
            print(f"{newsim.filename} failed: {error.stderr.decode('utf-8')}")
            raise(RuntimeError("Simulation Failure"))

        newsim.load()

        sses = []

        # FIXME: Make generic scores
        
        objectives_contain_times = True
        if self.objectives[0].get('times'):
            objectives_contain_times = False

        for obj in self.objectives:
            y = deep_get(newsim.root, obj.path)
            y = np.array(y).flatten()
            if objectives_contain_times:
                _, y0 = readChromatogram(obj.filename)
            else:
                y0 = readArray(obj.filename)

            sses.append(sse(y0, y))

        return sses
