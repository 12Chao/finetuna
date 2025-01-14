from ase.calculators.singlepoint import SinglePointCalculator as sp
from finetuna.calcs import DeltaCalc
from ase.io import write
import numpy as np
import subprocess
import re
import tempfile
import random


def convert_to_singlepoint(images):
    """
    Replaces the attached calculators with singlepoint calculators

    Parameters
    ----------

    images: list
        List of ase atoms images with attached calculators for forces and energies.
    """

    images = copy_images(images)
    singlepoint_images = []
    # cwd = os.getcwd()
    for image in images:
        if isinstance(image.get_calculator(), sp):
            singlepoint_images.append(image)
            continue
        # os.makedirs("./vasp_temp", exist_ok=True)
        # os.chdir("./vasp_temp")
        sample_energy = image.get_potential_energy(apply_constraint=False)
        sample_forces = image.get_forces(apply_constraint=False)
        if isinstance(image.get_calculator(), DeltaCalc):
            image.info["parent energy"] = image.get_calculator().parent_results[
                "energy"
            ]
            image.info["base energy"] = image.get_calculator().base_results["energy"]
            image.info["parent fmax"] = np.max(
                np.abs(image.get_calculator().parent_results["forces"])
            )

        sp_calc = sp(atoms=image, energy=float(sample_energy), forces=sample_forces)
        sp_calc.implemented_properties = ["energy", "forces"]
        image.set_calculator(sp_calc)
        # image.get_potential_energy()
        # image.get_forces()

        # image.calc.results["energy"] = float(image.calc.results["energy"])

        # sp_calc = sp(atoms=image, **image.calc.results)
        # sp_calc.implemented_properties = list(image.calc.results.keys())

        # image.set_calculator(sp_calc)
        singlepoint_images.append(image)
        # os.chdir(cwd)
        # os.system("rm -rf ./vasp_temp")

    return singlepoint_images


def compute_with_calc(images, calculator):
    """
    Calculates forces and energies of images with calculator.
    Returned images have singlepoint calculators.

    Parameters
    ----------

    images: list
        List of ase atoms images to be calculated.
    calculator: ase Calculator object
        Calculator used to get forces and energies.
    """

    images = copy_images(images)
    for image in images:
        image.set_calculator(calculator)
    return convert_to_singlepoint(images)


def subtract_deltas(images, base_calc, refs):
    """
    Produces the delta values of the image with precalculated values.
    This function is intended to be used by images that have
    precalculated forces and energies using the parent calc,
    that are attached to the image via a singlepoint calculator.
    This avoids having to recalculate results by a costly
    parent calc.

    Parameters
    ----------

    images: list
        List of ase atoms images to be calculated.
        Images should have singlepoint calculators with results.
    base_calc: ase Calculator object
        Calculator used as the baseline for taking delta subtraction.
    refs: list
        List of two images, they have results from parent and base calc
        respectively
    """

    images = copy_images(images)
    for image in images:
        parent_calc_sp = image.calc
        delta_sub_calc = DeltaCalc([parent_calc_sp, base_calc], "sub", refs)
        image.set_calculator(delta_sub_calc)
    return convert_to_singlepoint(images)


def copy_images(images):
    """
    Copies images and returns the new instances.
    The new images DO NOT have copied calculators.

    Parameters
    ----------

    images: list
        List of ase atoms images to be copied.
    """
    new_images = []
    for image in images:
        calc = image.get_calculator()
        new_image = image.copy()
        new_image.set_calculator(calc)
        new_images.append(new_image)
    return new_images


def get_fmax(forces: np.ndarray):
    return np.sqrt((forces**2).sum(axis=1).max())


def convert_to_top_k_forces(images, k):
    images = copy_images(images)
    singlepoint_images = []
    for image in images:
        top_k = np.sqrt((image.get_forces() ** 2).sum(axis=1))
        threshold = np.partition(top_k, -k)[-k]
        top_k[top_k < threshold] = 0
        top_k[top_k >= threshold] = 1
        top_k_forces = (image.get_forces().T * top_k).T

        sp_calc = sp(
            atoms=image, energy=float(image.get_potential_energy()), forces=top_k_forces
        )
        sp_calc.implemented_properties = ["energy", "forces"]
        image.set_calculator(sp_calc)
        singlepoint_images.append(image)
    return singlepoint_images


def write_to_db(database, queried_images, datatype="-", parentE="-", baseE="-"):
    for image in queried_images:
        database.write(
            image,
            key_value_pairs={"type": datatype, "parentE": parentE, "baseE": baseE},
        )


def write_to_db_online(
    database,
    queried_images,
    info,
    seed,
):
    random.seed(seed)
    for image in queried_images:
        dict_to_write = {
            "check": info.get("check"),
            "ml_energy": info.get("ml_energy"),
            "ml_fmax": info.get("ml_fmax", "-"),
            "parent_energy": info.get("parent_energy"),
            "parent_fmax": info.get("parent_fmax"),
            "force_uncertainty": info.get("force_uncertainty"),
            "energy_uncertainty": info.get("energy_uncertainty"),
            "dyn_uncertainty_tol": info.get("dyn_uncertainty_tol"),
            "stat_uncertain_tol": info.get("stat_uncertain_tol"),
            "tolerance": info.get("tolerance"),
        }
        for key, value in dict_to_write.items():
            if value is None:
                dict_to_write[key] = "-"
        database.write(
            image,
            key_value_pairs=dict_to_write,
            # id=seed,
        )


def calculate_rmsd(img1, img2):
    """
    Calculate rmsd between two images.
    (https://github.com/charnley/rmsd)

    Parameters
    ----------

    img1, img2: String or ase.Atoms
        Paths to the xyz files of the two images,
        or, ase.Atoms object, write them as xyz files.
    assuming img1 and img2 are the same type of objects.
    """
    if isinstance(img1, str):
        rmsd = subprocess.check_output(
            f"calculate_rmsd --reorder {img1} {img2}", shell=True
        )

    else:
        with tempfile.TemporaryDirectory() as tempdir:
            path1 = tempdir + "/img1.xyz"
            path2 = tempdir + "/img2.xyz"
            write(path1, img1)
            write(path2, img2)
            rmsd = subprocess.check_output(
                f"calculate_rmsd --reorder {path1} {path2}", shell=True
            )
    rmsd_float = re.findall("-?\ *[0-9]+\.?[0-9]*(?:[Ee]\ *-?\ *[0-9]+)?", str(rmsd))[0]
    return np.round(float(rmsd_float), 4)


def calculate_surface_k_points(atoms):
    cell = atoms.get_cell()
    order = np.inf
    a0 = np.linalg.norm(cell[0], ord=order)
    b0 = np.linalg.norm(cell[1], ord=order)
    multiplier = 40
    k_pts = (
        max(1, int(round(multiplier / a0))),
        max(1, int(round(multiplier / b0))),
        1,
    )
    return k_pts


def asedb_row_to_atoms(row):
    image = row.toatoms()
    sample_energy = row.parent_energy
    sample_forces = row.parent_forces
    sample_forces = np.array(
        [
            [float(f) for f in force.split(" ") if f != ""]
            for force in sample_forces[2:-2].split("]\n [")
        ]
    )
    sp_calc = sp(atoms=image, energy=float(sample_energy), forces=sample_forces)
    image.calc = sp_calc
    return image
