from dataclasses import dataclass, field
from chromoo.utils import readArray, readChromatogram

from typing import Optional, Tuple
import numpy as np

from chromoo.plotter import Plotter

@dataclass(init=True, order=True, repr=True, frozen=True)
class Objective: 
    """
    A class to store the objective paths and reference values, and evaluate a
    simulation's score. Can deal with both 1D (outlet) and ND (bulk) arrays as
    CADET paths. One NDarray objective can hold MULTIPLE actual objectives
    (thus a meta-objective). This makes defining the config file very easy.
    Assumes that time is the first axis.
    """
    name: str                                           # Objective name
    filename: str                                       # filename with objective reference values
    path: str                                           # dot-separated CADET Path 
    shape: tuple = field(default_factory=tuple)         # shape of data at path
    times: str = ''                                     # timestep data, if separate from objective reference
    combine_scores_axis: Optional[int] = None           # combine/avg scores along axis
    take: Optional[Tuple[int,int]] = None               # take a slice of sim data along (axis, index)
    combine_data_axis: Optional[int] = None
    score: str = 'sse'                                  # score type
    x0: np.ndarray = np.array([])                       # time steps
    y0: np.ndarray = np.array([])                       # data values

    def __post_init__(self): 
        """ 
        Read reference data if timestep data is separate or provided with the curves.
        Time data could be separated when dealing with, for instance, bulk output data, 
        which has a shape of (nts, ncol, nrad, ncomp). In that case, reshape
        the array to the given shape.
        """
        if self.times: 
            x0 = readArray(self.times)
            y0 = readArray(self.filename)

            if x0.shape == y0.shape: 
                object.__setattr__(self, 'shape', x0.shape)
            else: 
                y0 = y0.reshape(self.shape)

            object.__setattr__(self, 'x0', x0) 
            object.__setattr__(self, 'y0', y0)
        else: 
            x0, y0 = readChromatogram(self.filename)
            object.__setattr__(self, 'x0', x0)
            object.__setattr__(self, 'y0', y0)

            # NOTE: If multiple axially-averaged time-series reference data are given for each radial zone as separate objectives, self.take must be specified. But not for a simple 1D 1 objective case which also reads from chromatogram. A pre-emptive check would require us knowing the shape of the simulation output array.

    def verify(self, sim):
        """ Verify that the expected shape of simulation data matches with expected shape of reference data """
        pre_shape = np.array(sim.get_shape_pre(self.path))

        if self.take is not None: 
            pre_shape = np.delete(pre_shape, self.take[0])
            pre_shape = np.delete(pre_shape, np.where(pre_shape == 1))

        if self.combine_data_axis is not None: 
            pre_shape = np.delete(pre_shape, self.combine_data_axis)

        pre_shape = tuple(pre_shape)

        return pre_shape == self.y0.shape

    @property
    def n_obj(self): 
        """ Number of simple objectives generated by this class instance """
        # If shape is known, ignore time axis and compute product 
        # Otherwise, return 1 since we must be using single-objective time-series data.
        if self.shape: 
            return int(np.array(self.shape[1:]).prod())
        else: 
            return 1

    @property
    def names(self):
        if self.n_obj == 1: 
            return [ self.name ]
        else: 
            return [ f"{self.name}[{num}]" for num in range(self.n_obj) ]

    def process(self, sim): 
        """ Process the objective.path to return the sliced and averaged array, making it comparable to the reference data array """
        y = sim.get(self.path)

        # Allows using individual objectives representing slices of data
        # Eg. when ref. data (bulk output) is given as a radial section per objective.
        if self.take is not None: 
            y = np.take(y,indices=self.take[1], axis=self.take[0]).squeeze()

        # Allows averaging the simulation results. Useful if reference data is averaged.
        # Eg. Average the concentration along axial dim.
        if self.combine_data_axis is not None:
            y = np.average(y, axis=self.combine_data_axis)

        return y

    def evaluate(self, sim): 
        """ Evaluate a simulation based on reference objective data and score function """

        y0 = self.y0

        y = self.process(sim)

        sses = np.sum((y0 - y)**2, axis=0)

        if self.combine_scores_axis is not None: 
            sses = np.average(sses, axis=self.combine_scores_axis)

        return sses.ravel()

    def split(self, y): 
        """
        Split an NDarray objective path into several 1D arrays
        """
        # Move time axis to the end, and reshape array
        # This effectively splits the array into a bunch of time-series curves
        split_y = np.moveaxis(y, 0, -1).reshape(-1,y.shape[0])

        return split_y


    def plot(self, sim, ax): 
        t0 = self.x0
        y0 = self.y0
        y = self.process(sim)

        split_y0 = self.split(y0)
        split_y  = self.split(y)

        # WARNING: We assume timesteps are the same between reference and simulation.

        for i in range(self.n_obj): 
            ax.plot(t0, split_y0[i], label='reference')
            ax.plot(t0, split_y[i], label='simulation', ls='dashed')


    def plotsave(self, sim, fname="reference_simulation.pdf"): 
        """ Plot the solution vs reference plots for a given simulation """

        t0 = self.x0
        y0 = self.y0
        y = self.process(sim)

        split_y0 = self.split(y0)
        split_y  = self.split(y)

        # WARNING: We assume timesteps are the same between reference and simulation.

        plot = Plotter(title='Simulation vs Reference', cmap='tab20')
        for i in range(self.n_obj): 
            plot.plot(t0, split_y0[i], label='reference')
            plot.plot(t0, split_y[i], label='simulation', ls='dashed')

        plot.save(fname, dpi=300)
        plot.close()
