import numpy as np
import torch

import random


# from al_mlp.utils import write_to_db
from al_mlp.offline_learner.offline_learner import OfflineActiveLearner

# from torch.multiprocessing import Pool

torch.multiprocessing.set_sharing_strategy("file_system")


class UncertaintyLearner(OfflineActiveLearner):
    """Offline Active Learner using an uncertainty enabled ML potential to query
    data with the most uncertainty.
    Parameters
    ----------
    learner_settings: dict
        Dictionary of learner parameters and settings.

    trainer: object
        An isntance of a trainer that has a train and predict method.

    training_data: list
        A list of ase.Atoms objects that have attached calculators.
        Used as the first set of training data.

    parent_calc: ase Calculator object
        Calculator used for querying training data.

    base_calc: ase Calculator object
        Calculator used to calculate delta data for training.

    ensemble: int
        The number of models in ensemble
    """

    def __init__(
        self,
        learner_params,
        ml_potential,
        training_data,
        parent_calc,
        base_calc,
    ):
        super().__init__(
            learner_params, ml_potential, training_data, parent_calc, base_calc
        )

        self.ml_potential = ml_potential
        self.ensemble = learner_params.get("n_ensembles")
        self.parent_calls = 0

    def query_func(self):
        if self.iterations > 1:
            uncertainty = np.array(
                [atoms.info["max_force_stds"] for atoms in self.sample_candidates]
            )
            n_retrain = self.samples_to_retrain
            query_idx = np.argpartition(uncertainty, -1 * n_retrain)[-n_retrain:]
            queried_images = [self.sample_candidates[idx] for idx in query_idx]
        else:
            query_idx = random.sample(
                range(1, len(self.sample_candidates)),
                self.samples_to_retrain,
            )
            queried_images = [self.sample_candidates[idx] for idx in query_idx]

        return queried_images
