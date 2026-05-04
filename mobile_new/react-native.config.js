const {
  projectConfig: androidProjectConfig,
  dependencyConfig: androidDependencyConfig,
} = require('@react-native-community/cli-platform-android');
const {
  projectConfig: iosProjectConfig,
  dependencyConfig: iosDependencyConfig,
} = require('@react-native-community/cli-platform-ios');

module.exports = {
  platforms: {
    android: {
      projectConfig: androidProjectConfig,
      dependencyConfig: androidDependencyConfig,
    },
    ios: {
      projectConfig: iosProjectConfig,
      dependencyConfig: iosDependencyConfig,
    },
  },
};
