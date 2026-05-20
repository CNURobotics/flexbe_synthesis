## Summary

- 

## Validation

- [ ] `colcon build --symlink-install --packages-up-to flexbe_synthesis`
- [ ] `colcon test --packages-select flexbe_synthesis flexbe_synthesis_msgs flexbe_synthesis_core flexbe_synthesis_generic flexbe_synthesis_slugs flexbe_synthesis_examples`
- [ ] `colcon test-result --verbose`

## Release Impact

- [ ] Package metadata updated if needed
- [ ] README or package docs updated if behavior changed
- [ ] New dependencies declared in `package.xml`
- [ ] Launch/YAML examples checked if touched
