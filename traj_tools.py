"""
===============================================================================
                                AMBER TRAJECTORY TOOLS
===============================================================================

    - PyTraj based analysis tools for Amber trajectories
"""

import numpy as np
import pytraj as pt
import subprocess
from glob import glob


def _load_structure(in_str):
    # .pdb only req. 1 input
    if isinstance(in_str, str) and '.pdb' in in_str:
        return pt.load(in_str)
    # .r and same named .top
    elif isinstance(in_str, str):
        return pt.load(in_str, in_str.split('.')[0]+'.top')
    # Explicitly specified .crd and .top
    elif isinstance(in_str, list) and len(in_str) == 2:
        return pt.load(in_str[0], in_str[1])
    # For references, can just be int i.e. frame no.
    elif isinstance(in_str, int):
        return in_str
    # If not any of the above raise an error
    else:
        raise ValueError("Structure not recognised")


def _run_cpptraj(directory, input_file):
    # Print a starting message
    print(f"STARTING  | CPPTRAJ with input:  {input_file}")
    # Run CPPTRAJ
    try:
        subprocess.run(f"cpptraj -i {directory}/{input_file}",
                       shell=True, check=True)
    except subprocess.CalledProcessError as error:
        print('Error code:', error.returncode,
              '. Output:', error.output.decode("utf-8"))
    # Print another message when finished successfully
    print(f"COMPLETED | CPPTRAJ with input:  {input_file}")


def _traj_align(trj_path, top, out_path=None, ref_str=None,
                aln_mask='@CA,C,N,O'):
    # Load the trajectory w. topology
    full_trj = pt.iterload(trj_path, top)
    print(f'Loaded trajectory: {trj_path}')
    if ref_str is not None:
        full_trj = pt.align(full_trj, mask=aln_mask, ref=ref_str)
    else:
        full_trj = pt.align(full_trj, mask=aln_mask)
    write_name = out_path if out_path is not None else trj_path
    pt.write_traj(write_name, full_trj, overwrite=True)
    print(f'Saved new trajectory: {write_name}')


def make_fulltraj(directory, ref_str):
    # Get file base name from dir. name
    stem = directory.split('/')[-1]
    # Count the number of md steps run
    n_steps = len(glob(f"{directory}/{stem}.md_*.x"))
    # Check stem is correct and files are found
    assert n_steps > 0, 'Not enough md files'
    # Display info that will be used
    print(f" Making fulltraj for {stem} with {n_steps} steps.")
    file1 = []
    # Load topology
    file1.append(f"parm {directory}/{stem}.top")
    # Load each trajectory step
    for i in np.arange(n_steps)+1:
        file1.append(f"trajin {directory}/{stem}.md_{i}.x")
    # Load reference structure (.top + .r)
    if isinstance(ref_str, list):
        file1.append(f"parm {ref_str[0]} [refparm]")
        file1.append(f"reference {ref_str[1]} parm [refparm]")
    # Load reference structure (.pdb)
    else:
        file1.append(f"reference {ref_str}")
    # Post-processing
    file1 += ['autoimage', 'rms reference @CA,C,N,O', 'strip :WAT,Na+,Cl-']
    # Output
    file1.append(f"trajout {directory}/{stem}_{n_steps*5}ns_dry.nc netcdf")
    file1.append("go")
    # Write all to cpptraj input file
    with open(f"{directory}/fulltraj.in", 'w+') as file:
        file.writelines('\n'.join(file1))
    # Run cpptraj using that input file
    _run_cpptraj(directory, 'fulltraj.in')


def align(in_str, ref_str, out_str, aln_mask='@CA,C,N,O', strip_mask=None):
    # Load the initial structure
    to_align = _load_structure(in_str)
    ref = _load_structure(ref_str)
    # Run the alignment
    aligned = pt.align(to_align, mask=aln_mask, ref=ref)
    # aligned = aligned.autoimage()
    # If a strip is required, perform the strip
    if strip_mask is not None:
        aligned = aligned.strip(strip_mask)
    # Write the new structure
    pt.write_traj(out_str, aligned, overwrite=True)


def snapshot_pdbs(directory, trj_path, top_path, ref_str, snapshots):
    # Make the directory for the output
    try:
        subprocess.run(f"mkdir -p {directory}/snapshots/",
                       shell=True, check=True)
    except subprocess.CalledProcessError as error:
        print('Error code:', error.returncode,
              '. Output:', error.output.decode("utf-8"))
    stem = trj_path.split('/')[-1].split('.')[0]
    if isinstance(snapshots[0], int):
        print('oops')
    elif isinstance(snapshots[0], list):
        for snl in snapshots:
            file1 = []
            file1.append(f"parm {top_path}")
            file1.append(f"trajin {trj_path} {' '.join([str(i) for i in snl])}")
            # Load reference structure (.top + .r)
            if isinstance(ref_str, list):
                file1.append(f"parm {ref_str[0]} [refparm]")
                file1.append(f"reference {ref_str[1]} parm [refparm]")
            # Load reference structure (.pdb)
            else:
                file1.append(f"reference {ref_str}")
            file1.append('rms reference @CA,C,N,O')
            file1.append(f"trajout {directory}/snapshots/{stem}.pdb multi chainid A")
            file1.append("go")
            # Write all to cpptraj input file
            with open(f"{directory}/sn{snl[0]}.in", 'w') as file:
                file.writelines('\n'.join(file1))
            # Run cpptraj using that input file
            _run_cpptraj(directory, f"sn{snl[0]}.in")
            snaps = np.arange(snl[0], snl[1], snl[2])
            for i in np.arange(len(snaps)):
                print(i, snaps[i])
                try:
                    subprocess.run(' '.join(['mv',
                                   f"{directory}/snapshots/{stem}.pdb.{i+1}",
                                   f"{directory}/snapshots/{stem}_{snaps[i]/200:.0f}ns.pdb"]),
                                   shell=True, check=True)
                except subprocess.CalledProcessError as error:
                    print('Error code:', error.returncode,
                          '. Output:', error.output.decode("utf-8"))
            # Align all output structures
            for path in glob(f"{directory}/snapshots/*.pdb"):
                align(path,
                      f"{directory}/snapshots/{stem}_{snapshots[0][0]/200:.0f}ns.pdb",
                      path)


def cut_traj(trj_path, top, out_path, denom=100, split=False, strip_mask=None):
    # Load the trajectory w. topology and run autoimage
    full_trj = pt.iterload(trj_path, top)
    full_trj = full_trj.autoimage()
    print(f'Loaded trajectory: {trj_path}')
    if not split:
        start_point = 1
        print(f'NOT cutting traj so starting from {start_point}')
        N = int(full_trj.n_frames/denom)
    else:
        start_point = int(full_trj.n_frames/2)
        print(f'CUTTING traj, starting from {start_point}')
        N = int(start_point/denom)
    print(f'Writing {N} frames')
    frames = np.linspace(start_point, full_trj.n_frames, num=N, dtype=int)-1
    # If a strip is required, perform the strip
    if strip_mask is not None:
        full_trj = full_trj.strip(strip_mask)
    pt.write_traj(out_path, full_trj, frame_indices=frames, overwrite=True)
    print(f'Saved new trajectory: {out_path}')


def measure_rmsd(trj_path, top_path, ref_str, rmsd_mask,
                 aln_mask='@CA,C,N,O', nofit=True):
    # Load the trajectory w. topology
    traj = pt.iterload(trj_path, top_path)
    # Load ref. structure if path is given
    ref = _load_structure(ref_str)
    # Run autoimage to cluster and centre traj.
    traj = traj.autoimage()
    # Align the traj. using backbone atoms
    traj = pt.align(traj, mask=aln_mask, ref=ref)
    # Calculate the rmsd
    data = pt.rmsd(traj, mask=rmsd_mask, ref=ref, nofit=nofit)
    return data


def measure_rmsf(trj_path, top_path, ref_str, rmsf_mask, aln_mask='@CA,C,N,O'):
    # Load the trajectory w. topology
    traj = pt.iterload(trj_path, top_path)
    # Load ref. structure if path is given
    ref = _load_structure(ref_str)
    # Run autoimage to cluster and centre traj.
    traj = traj.autoimage()
    # Align the traj. using backbone atoms
    traj = pt.align(traj, mask=aln_mask, ref=ref)
    # Calculate the rmsf values
    data = pt.rmsf(traj, mask=rmsf_mask, options='byres')
    return data


def extract_frame(trj_path, top, out_path,
                  ref_str=None, split=False, strip_mask=None, frame='final'):
    # Load the trajectory w. topology and run autoimage
    full_trj = pt.iterload(trj_path, top)
    full_trj = full_trj.autoimage()
    print(f'Loaded trajectory: {trj_path}')
    # Calculate frame to extract
    N = int(full_trj.n_frames)-1 if frame == 'final' else int(frame)-1
    print(f'Writing {N+1}th frame as pbd')
    # Save the new trajectory file
    pt.write_traj(out_path, full_trj, frame_indices=[N], overwrite=True)
    print(f'Saved new trajectory: {out_path}')


def measure_distance(trj_path, top_path, atom_pair, ref_str,
                     aln_mask='@CA,C,N,O'):
    # Load the trajectory w. topology
    traj = pt.iterload(trj_path, top_path)
    # Load ref. structure if path is given
    ref = _load_structure(ref_str)
    # Run autoimage to cluster and centre traj.
    traj = traj.autoimage()
    # Align the traj. using backbone atoms
    traj = pt.align(traj, mask=aln_mask, ref=ref)
    # Calculate distance (A) between two pairs/groups
    data = pt.distance(traj, f"{atom_pair[0]} {atom_pair[1]}")
    return data


def measure_angle(trj_path, top_path, angle_atoms, ref_str,
                  aln_mask='@CA,C,N,O'):
    # Check that correct atom/res mask is defined
    n_atoms = len(angle_atoms.split())
    assert n_atoms in [3, 4], "INPUT ERROR: Must have 3 or 4 atom groups."
    # Load the trajectory w. topology
    traj = pt.iterload(trj_path, top_path)
    # Load ref. structure if path is given
    ref = _load_structure(ref_str)
    # Run autoimage to cluster and centre traj.
    traj = traj.autoimage()
    # Align the traj. using backbone atoms
    traj = pt.align(traj, mask=aln_mask, ref=ref)
    # Calculate angle between set of atoms
    if n_atoms == 3:
        print("Calculating angle between 3 atom groups.")
        data = pt.angle(traj=traj, mask=angle_atoms)
    else:
        print("Calculating dihedral angle between 4 atom groups.")
        data = pt.dihedral(traj=traj, mask=angle_atoms)
    return data


def read_pdb(path):
    # Load complex pdb to edit
    with open(path, 'r') as f:
        lines = f.readlines()
    print(f'Loaded {path}')
    lines = [line.split() for line in lines]
    return lines


def _process_atm_nm(name):
    # Full length names are left unchanged
    if len(name) == 4:
        return name
    # Otherwise align to second character
    else:
        return f" {name:<3}"


def format_pdb(info):
    # Process atom name seperately
    atm_nm = _process_atm_nm(info[2])

    # Assign values for each column
    record = info[0]  # Record name
    atm_id = info[1]  # Atom serial number
    alt_li = ' '  # Alternate location indicator
    res_nm = info[3]  # Residue name.
    chn_id = ' '  # Chain ID
    res_id = info[4]  # Residue sequence number
    i_code = ' '   # Code for insertion
    coords = [float(info[5]),  # x (A)
              float(info[6]),  # y (A)
              float(info[7])]  # z (A)
    occupn = float(info[8])  # Occupancy
    temprt = float(info[9])  # Temperature
    elemnt = info[10]  # Element
    charge = '  '  # Charge

    # Format the new line using all the values
    new_line = (f"{record:6}"
                f"{atm_id:>5} "
                f"{atm_nm:4}"
                f"{alt_li}"
                f"{res_nm:3} "
                f"{chn_id}"
                f"{res_id:>4}"
                f"{i_code}   "
                f"{coords[0]:>8.3f}{coords[1]:>8.3f}{coords[2]:>8.3f}"
                f"{occupn:>6.2f}"
                f"{temprt:>6.2f}          "
                f"{elemnt:>2}"
                f"{charge}\n")

    # Return the new line
    return new_line
