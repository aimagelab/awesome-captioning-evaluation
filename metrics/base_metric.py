from abc import ABC, abstractmethod

class BaseMetric(ABC):
    @abstractmethod
    def load_model(self, **kwargs):
        pass
    
    @abstractmethod
    def compute_score(self, *args, **kwargs):
        pass
