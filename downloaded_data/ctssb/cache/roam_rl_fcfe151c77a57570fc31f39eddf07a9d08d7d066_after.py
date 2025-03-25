import configparser
import argparse
from roam_rl.utils.path_generator import PathGenerator
from roam_rl.openai_baselines.ppo import PPO
import os
import ast
from roam_utils.provenance import config_helpers


def main(args):
    run_config_file = args.config_file
    run_config_data = configparser.ConfigParser()
    run_config_data.read(run_config_file)
    experiment_no = run_config_data.get('experiment', 'experiment_no')
    robot_name = run_config_data.get('experiment', 'robot_name')
    experiment_dir = PathGenerator.get_ppo_experiment_dir(os.environ["EXPERIMENTS_DIR"], robot_name, experiment_no)
    load_model_seed = run_config_data.get('experiment', 'load_model_seed')

    env_seed = run_config_data.getint('experiment', 'env_seed')
    copy_sections = ast.literal_eval(run_config_data.get('experiment', 'copy_sections'))

    config_file = PathGenerator.get_config_pathname(experiment_dir, experiment_no)
    assert os.path.exists(config_file), 'config file does not exist'

    config_data = configparser.ConfigParser()
    config_data.read(config_file)
    for section in copy_sections:
        config_helpers.copy_section_from_old_config_to_new_config(old_config=run_config_data, new_config=config_data,
                                                                  section=section, overwrite=True)

    ppo_section_name = config_data.get('experiment', 'ppo')
    ppo = PPO(config_data, ppo_section_name)
    ppo.set_experiment_dir(experiment_dir)

    model, env = ppo.load(model_seed=load_model_seed, env_seed=env_seed)
    ppo.run(model=model, env=env)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('config_file', help='A string specifying the path to a config file')
    arg = parser.parse_args()
    main(arg)
